from __future__ import annotations

import hashlib
import json
import re

from specimpact.llm_graph.schemas import AliasCandidate
from specimpact.models import Entity, Evidence, Relation
from specimpact.store import LocalStore


def suggest_alias_candidates(store: LocalStore, *, use_llm: bool = False) -> int:
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
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
        aliases = sorted(
            {
                value
                for item in unique.values()
                for value in [item.display_name, item.canonical_name, *item.aliases]
                if value and value not in {target.display_name, target.entity_id}
            }
        )
        evidence_ids = sorted(
            {
                evidence_id
                for relation in relations
                if relation.target_id in unique
                for evidence_id in relation.evidence_ids
                if evidence_id in evidence
            }
        )
        rows.append(
            AliasCandidate(
                candidate_id=f"alias_{_short_hash(group + target.entity_id)}",
                target_id=target.entity_id,
                aliases=aliases,
                judgement="same" if use_llm else "unsure",
                evidence_ids=evidence_ids,
                reason=f"similar concept key: {group}",
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

        for alias in candidate.aliases:
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


def _is_ascii(value: str) -> bool:
    return all(ord(char) < 128 for char in value)


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
