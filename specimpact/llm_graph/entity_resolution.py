from __future__ import annotations

import hashlib
import json
import re

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
    by_group: dict[str, list[Entity]] = {}
    for entity in entities:
        key = _concept_key(entity.display_name, entity.canonical_name)
        if key:
            by_group.setdefault(key, []).append(entity)
    rows: list[AliasCandidate] = []
    for group, items in by_group.items():
        unique = {item.entity_id: item for item in items}
        if len(unique) < 2:
            continue
        target = sorted(
            unique.values(),
            key=lambda item: (_is_ascii(item.display_name), item.entity_id),
        )[0]
        for candidate in sorted(unique.values(), key=lambda item: item.entity_id):
            if candidate.entity_id == target.entity_id:
                continue
            pair_ids = {target.entity_id, candidate.entity_id}
            aliases = sorted(
                {
                    value
                    for value in [
                        candidate.display_name,
                        candidate.canonical_name,
                        *candidate.aliases,
                    ]
                    if value
                    and value
                    not in {target.display_name, target.canonical_name, target.entity_id}
                }
            )
            pair_relations = [
                relation
                for relation in relations
                if relation.source_id in pair_ids
                or relation.target_id in pair_ids
                or relation.source_id in _surrounding_nodes(relations, pair_ids)
                or relation.target_id in _surrounding_nodes(relations, pair_ids)
            ][:24]
            evidence_ids = sorted(
                {
                    evidence_id
                    for relation in pair_relations
                    for evidence_id in relation.evidence_ids
                    if evidence_id in evidence
                }
            )
            surrounding_node_ids = _surrounding_nodes(relations, pair_ids)
            evidence_quotes = [evidence[evidence_id].quote for evidence_id in evidence_ids[:8]]
            relation_context = [_relation_context(relation) for relation in pair_relations]
            judgement = AliasJudgement(
                judgement="unsure",
                reason=f"similar concept key: {group}",
            )
            if client:
                judgement = client.structured(
                    "alias_resolution",
                    {
                        "entity_a": _entity_payload(target),
                        "entity_b": _entity_payload(candidate),
                        "relations": [relation.model_dump() for relation in pair_relations],
                        "relation_context": relation_context,
                        "evidence": [
                            {
                                "evidence_id": evidence_id,
                                "quote": evidence[evidence_id].quote,
                                "file": evidence[evidence_id].source_location.file,
                            }
                            for evidence_id in evidence_ids[:8]
                        ],
                        "instruction": (
                            "Judge whether entity_a and entity_b are the same business or "
                            "system concept. Return same only when they should become aliases. "
                            "Return related for connected but distinct fields, and different "
                            "for separate concepts. Use only supplied evidence and relation "
                            "context."
                        ),
                    },
                    AliasJudgement,
                )
            clean_evidence_ids = [
                evidence_id for evidence_id in judgement.evidence_ids if evidence_id in evidence
            ] or evidence_ids
            rows.append(
                AliasCandidate(
                    candidate_id=(
                        f"alias_{_short_hash(group + target.entity_id + candidate.entity_id)}"
                    ),
                    target_id=target.entity_id,
                    aliases=aliases,
                    judgement=judgement.judgement,
                    evidence_ids=clean_evidence_ids,
                    reason=judgement.reason or f"similar concept key: {group}",
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
    if any(token in folded for token in ("creditlimit", "credit_limit", "limit_amt")):
        return "credit_limit"
    if "限度" in text and "額" in text:
        return "credit_limit"
    if "電話" in text or "phone" in folded:
        return "phone_number"
    if "本人確認" in text or "identity" in folded or "kyc" in folded:
        return "identity_verification"
    ascii_tokens = re.findall(r"[a-z][a-z0-9]*", folded)
    if {"credit", "limit"} <= set(ascii_tokens):
        return "credit_limit"
    if len(canonical_name) >= 4:
        return canonical_name.replace("_", "")
    return ""


def _entity_payload(entity: Entity) -> dict[str, object]:
    return {
        "entity_id": entity.entity_id,
        "entity_type": entity.entity_type,
        "display_name": entity.display_name,
        "canonical_name": entity.canonical_name,
        "aliases": entity.aliases,
        "source_document_ids": entity.source_document_ids,
    }


def _surrounding_nodes(relations: list[Relation], entity_ids: set[str]) -> list[str]:
    result = set()
    for relation in relations:
        if relation.source_id in entity_ids:
            result.add(relation.target_id)
        if relation.target_id in entity_ids:
            result.add(relation.source_id)
    return sorted(result)


def _relation_context(relation: Relation) -> str:
    return (
        f"{relation.source_id} -{relation.relation_type}-> {relation.target_id} "
        f"[{relation.status}/{relation.polarity}]"
    )


def _is_ascii(value: str) -> bool:
    return all(ord(char) < 128 for char in value)


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
