from __future__ import annotations

import hashlib
import json
import math
import re
from itertools import combinations

from specimpact.graphrag import LLMClient, client_from_config
from specimpact.llm_graph.schemas import AliasCandidate, AliasJudgement
from specimpact.models import Entity, Evidence, Relation
from specimpact.store import LocalStore


def suggest_alias_candidates(
    store: LocalStore,
    *,
    use_llm: bool = False,
    llm_client: LLMClient | None = None,
) -> int:
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    client = llm_client or (client_from_config(store) if use_llm else None)
    rows: list[AliasCandidate] = []

    for left, right in combinations(sorted(entities, key=lambda item: item.entity_id), 2):
        signals = _alias_signals(left, right, relations, evidence)
        if not signals:
            continue
        target, candidate = _target_and_candidate(left, right)
        pair_ids = {target.entity_id, candidate.entity_id}
        surrounding_node_ids = _surrounding_nodes(relations, pair_ids)
        pair_relations = _pair_relations(relations, pair_ids, surrounding_node_ids)
        evidence_ids = _pair_evidence_ids(pair_relations, evidence)
        evidence_ids = sorted(
            {*evidence_ids, *_nearby_evidence_ids(left, right, relations, evidence)}
        )
        evidence_quotes = [evidence[evidence_id].quote for evidence_id in evidence_ids[:8]]
        relation_context = [_relation_context(relation) for relation in pair_relations]
        reason = f"candidate signals: {', '.join(signals)}"
        judgement = AliasJudgement(judgement="unsure", reason=reason)
        if client:
            judgement = client.structured(
                "alias_resolution",
                {
                    "entity_a": _entity_payload(target),
                    "entity_b": _entity_payload(candidate),
                    "candidate_signals": signals,
                    "relations": [relation.model_dump() for relation in pair_relations],
                    "relation_context": relation_context,
                    "evidence": [
                        {
                            "evidence_id": evidence_id,
                            "quote": evidence[evidence_id].quote,
                            "file": evidence[evidence_id].source_location.file,
                            "line_start": evidence[evidence_id].source_location.line_start,
                            "line_end": evidence[evidence_id].source_location.line_end,
                        }
                        for evidence_id in evidence_ids[:8]
                    ],
                    "instruction": (
                        "Judge whether entity_a and entity_b are the same business or "
                        "system concept. Return same only when they should become aliases. "
                        "Return related for connected but distinct fields, and different "
                        "for separate concepts. Candidate signals are recall-oriented hints, "
                        "not proof. Use only supplied evidence and relation context."
                    ),
                },
                AliasJudgement,
            )
        clean_evidence_ids = [
            evidence_id for evidence_id in judgement.evidence_ids if evidence_id in evidence
        ] or evidence_ids
        group_key = "|".join(sorted(signals))
        rows.append(
            AliasCandidate(
                candidate_id=(
                    f"alias_{_short_hash(group_key + target.entity_id + candidate.entity_id)}"
                ),
                target_id=target.entity_id,
                aliases=_candidate_aliases(target, candidate),
                judgement=judgement.judgement,
                evidence_ids=clean_evidence_ids,
                reason=judgement.reason or reason,
                entity_a_id=target.entity_id,
                entity_b_id=candidate.entity_id,
                compared_entity_ids=sorted(pair_ids),
                surrounding_node_ids=surrounding_node_ids,
                relation_context=relation_context,
                evidence_quotes=evidence_quotes,
                llm_reason=judgement.reason if client else "",
                confidence_label=judgement.confidence_label,
            )
        )
    store.write(
        "alias_candidates",
        _merge_candidates(store.read("alias_candidates", AliasCandidate), rows),
    )
    return len(rows)


def list_alias_candidates(store: LocalStore) -> str:
    return json.dumps(
        [item.model_dump() for item in store.read("alias_candidates", AliasCandidate)],
        ensure_ascii=False,
        indent=2,
    )


def decide_alias_candidate(store: LocalStore, candidate_id: str, status: str) -> AliasCandidate:
    if status not in {"confirmed", "rejected"}:
        raise ValueError("status must be confirmed or rejected")
    candidates = store.read("alias_candidates", AliasCandidate)
    candidate = next((item for item in candidates if item.candidate_id == candidate_id), None)
    if not candidate:
        raise ValueError(f"Unknown alias candidate: {candidate_id}")
    candidate.status = status  # type: ignore[assignment]
    store.write("alias_candidates", candidates)
    if status == "confirmed":
        from specimpact.inspection import decide_alias

        aliases = candidate.aliases if candidate.judgement == "same" else []
        for alias in aliases:
            decide_alias(store, candidate.target_id, alias, "approved")
    return candidate


def _alias_signals(
    left: Entity,
    right: Entity,
    relations: list[Relation],
    evidence: dict[str, Evidence],
) -> list[str]:
    signals = set()
    left_key = _concept_key(left.display_name, left.canonical_name)
    right_key = _concept_key(right.display_name, right.canonical_name)
    if left_key and left_key == right_key:
        signals.add(f"concept_key:{left_key}")
    left_tokens = _entity_tokens(left)
    right_tokens = _entity_tokens(right)
    overlap = left_tokens & right_tokens
    if _meaningful_overlap(overlap):
        signals.add(f"name_token_overlap:{','.join(sorted(overlap)[:4])}")
    if _canonical_shape(left) == _canonical_shape(right) and _canonical_shape(left):
        signals.add("camel_snake_shape_match")
    similarity = _embedding_like_similarity(_entity_text(left), _entity_text(right))
    if similarity >= 0.72:
        signals.add(f"embedding_similarity:{similarity:.2f}")
    relation_score = _relation_similarity(left.entity_id, right.entity_id, relations)
    if relation_score >= 0.4:
        signals.add(f"relation_similarity:{relation_score:.2f}")
    if _nearby_evidence_ids(left, right, relations, evidence):
        signals.add("same_evidence_neighborhood")
    return sorted(signals)


def _merge_candidates(
    current: list[AliasCandidate],
    incoming: list[AliasCandidate],
) -> list[AliasCandidate]:
    by_id = {item.candidate_id: item for item in current}
    for item in incoming:
        if item.candidate_id not in by_id:
            by_id[item.candidate_id] = item
    return list(by_id.values())


def _concept_key(display_name: str, canonical_name: str) -> str:
    text = f"{display_name} {canonical_name}"
    folded = text.casefold()
    normalized = _canonical_shape_text(text)
    token_set = set(_split_identifier_tokens(text))
    if any(token in normalized for token in ("creditlimit", "requestedcreditlimit", "limitamt")):
        return "credit_limit"
    if "利用限度額" in text or "希望利用限度額" in text:
        return "credit_limit"
    if {"credit", "limit"} <= token_set:
        return "credit_limit"
    if "phone" in folded or "tel" in folded or "電話" in text:
        return "phone_number"
    if "identity" in folded or "kyc" in folded or "本人確認" in text:
        return "identity_verification"
    if canonical_name and len(canonical_name) >= 4:
        return _canonical_shape_text(canonical_name)
    return ""


def _target_and_candidate(left: Entity, right: Entity) -> tuple[Entity, Entity]:
    ordered = sorted(
        [left, right],
        key=lambda item: (_is_ascii(item.display_name), len(item.display_name), item.entity_id),
    )
    return ordered[0], ordered[1]


def _candidate_aliases(target: Entity, candidate: Entity) -> list[str]:
    return sorted(
        {
            value
            for value in [candidate.display_name, candidate.canonical_name, *candidate.aliases]
            if value and value not in {target.display_name, target.canonical_name, target.entity_id}
        }
    )


def _entity_payload(entity: Entity) -> dict[str, object]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "display_name": entity.display_name,
        "canonical_name": entity.canonical_name,
        "aliases": entity.aliases,
        "source_document_ids": entity.source_document_ids,
    }


def _entity_text(entity: Entity) -> str:
    return " ".join([entity.display_name, entity.canonical_name, *entity.aliases])


def _entity_tokens(entity: Entity) -> set[str]:
    return set(_split_identifier_tokens(_entity_text(entity)))


def _split_identifier_tokens(value: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]*|\d+|[一-龥ぁ-んァ-ン]+", spaced)
    result: list[str] = []
    for token in tokens:
        folded = token.casefold()
        result.extend(part for part in re.split(r"[_\W]+", folded) if len(part) >= 2)
    return result


def _meaningful_overlap(tokens: set[str]) -> bool:
    stop = {"id", "no", "name", "field", "item", "value", "code", "type"}
    return any(token not in stop and (len(token) >= 4 or not _is_ascii(token)) for token in tokens)


def _canonical_shape(entity: Entity) -> str:
    return _canonical_shape_text(_entity_text(entity))


def _canonical_shape_text(value: str) -> str:
    return "".join(_split_identifier_tokens(value))


def _embedding_like_similarity(left: str, right: str) -> float:
    left_grams = _char_grams(_canonical_shape_text(left), 3)
    right_grams = _char_grams(_canonical_shape_text(right), 3)
    if not left_grams or not right_grams:
        return 0.0
    return _cosine(left_grams, right_grams)


def _char_grams(value: str, width: int) -> dict[str, float]:
    if len(value) < width:
        return {value: 1.0} if value else {}
    result: dict[str, float] = {}
    for index in range(len(value) - width + 1):
        gram = value[index : index + width]
        result[gram] = result.get(gram, 0.0) + 1.0
    return result


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    denominator = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    if not denominator:
        return 0.0
    return sum(left.get(key, 0.0) * right.get(key, 0.0) for key in keys) / denominator


def _relation_similarity(left_id: str, right_id: str, relations: list[Relation]) -> float:
    left_context = _relation_signature(left_id, relations)
    right_context = _relation_signature(right_id, relations)
    if not left_context or not right_context:
        return 0.0
    overlap = left_context & right_context
    return len(overlap) / len(left_context | right_context)


def _relation_signature(entity_id: str, relations: list[Relation]) -> set[str]:
    signature = set()
    for relation in relations:
        if relation.source_id == entity_id:
            signature.add(f"out:{relation.relation_type}:{_node_family(relation.target_id)}")
        if relation.target_id == entity_id:
            signature.add(f"in:{relation.relation_type}:{_node_family(relation.source_id)}")
    return signature


def _node_family(node_id: str) -> str:
    return node_id.split(".", 1)[0]


def _nearby_evidence_ids(
    left: Entity,
    right: Entity,
    relations: list[Relation],
    evidence: dict[str, Evidence],
) -> list[str]:
    left_ids = _entity_evidence_ids(left.entity_id, relations)
    right_ids = _entity_evidence_ids(right.entity_id, relations)
    shared = left_ids & right_ids
    result = set(shared)
    for left_id in left_ids:
        left_ev = evidence.get(left_id)
        if not left_ev:
            continue
        for right_id in right_ids:
            right_ev = evidence.get(right_id)
            if not right_ev or left_ev.source_location.file != right_ev.source_location.file:
                continue
            if abs(left_ev.source_location.line_start - right_ev.source_location.line_start) <= 3:
                result.update({left_id, right_id})
    return sorted(result)


def _entity_evidence_ids(entity_id: str, relations: list[Relation]) -> set[str]:
    return {
        evidence_id
        for relation in relations
        if relation.source_id == entity_id or relation.target_id == entity_id
        for evidence_id in relation.evidence_ids
    }


def _surrounding_nodes(relations: list[Relation], entity_ids: set[str]) -> list[str]:
    result = set()
    for relation in relations:
        if relation.source_id in entity_ids:
            result.add(relation.target_id)
        if relation.target_id in entity_ids:
            result.add(relation.source_id)
    return sorted(result)


def _pair_relations(
    relations: list[Relation],
    pair_ids: set[str],
    surrounding_node_ids: list[str],
) -> list[Relation]:
    context_ids = pair_ids | set(surrounding_node_ids)
    return [
        relation
        for relation in relations
        if relation.source_id in context_ids or relation.target_id in context_ids
    ][:24]


def _pair_evidence_ids(
    pair_relations: list[Relation],
    evidence: dict[str, Evidence],
) -> list[str]:
    return sorted(
        {
            evidence_id
            for relation in pair_relations
            for evidence_id in relation.evidence_ids
            if evidence_id in evidence
        }
    )


def _relation_context(relation: Relation) -> str:
    return (
        f"{relation.source_id} -{relation.relation_type}-> {relation.target_id} "
        f"[{relation.status}/{relation.polarity}]"
    )


def _is_ascii(value: str) -> bool:
    return all(ord(char) < 128 for char in value)


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
