from __future__ import annotations

import json

import yaml

from specimpact.core import resolve_name
from specimpact.extraction import AliasCatalog
from specimpact.llm_graph.entity_resolution import (
    decide_alias_candidate,
    list_alias_candidates,
    suggest_alias_candidates,
)
from specimpact.models import Artifact, Entity, Evidence, Relation
from specimpact.store import LocalStore


def suggest_aliases(store: LocalStore, *, use_llm: bool = False) -> int:
    if use_llm:
        return suggest_alias_candidates(store, use_llm=True)
    path = store.root / "alias_suggestions.jsonl"
    rows = [
        {"target_id": item.artifact_id, "alias": item.display_name, "status": "pending"}
        for item in store.read("artifacts", Artifact)
        if item.display_name not in item.aliases
    ]
    store.write_text(
        path,
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    return len(rows)


def review_alias_candidates(store: LocalStore) -> str:
    return list_alias_candidates(store)


def confirm_alias_candidate(store: LocalStore, candidate_id: str):
    return decide_alias_candidate(store, candidate_id, "confirmed")


def reject_alias_candidate(store: LocalStore, candidate_id: str):
    return decide_alias_candidate(store, candidate_id, "rejected")


def list_aliases(store: LocalStore) -> str:
    aliases = (store.root / "aliases.yml").read_text(encoding="utf-8")
    suggestions = store.root / "alias_suggestions.jsonl"
    pending = suggestions.read_text(encoding="utf-8") if suggestions.exists() else ""
    return f"Manual aliases:\n{aliases}\nSuggestions:\n{pending}"


def decide_alias(store: LocalStore, target_id: str, alias: str, status: str) -> None:
    rendered_aliases = None
    if status == "approved":
        alias_path = store.root / "aliases.yml"
        data = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}
        item = data.setdefault("aliases", {}).setdefault(
            target_id,
            {"canonical_type": _target_type(store, target_id), "aliases": []},
        )
        if alias not in item.setdefault("aliases", []):
            item["aliases"].append(alias)
        rendered_aliases = yaml.safe_dump(data, allow_unicode=True, sort_keys=True)
        AliasCatalog.parse(rendered_aliases, alias_path)
    path = store.root / "alias_suggestions.jsonl"
    rows = (
        [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if path.exists()
        else []
    )
    matched = False
    for row in rows:
        if row["target_id"] == target_id and row["alias"] == alias:
            row["status"] = status
            matched = True
    if not matched:
        rows.append({"target_id": target_id, "alias": alias, "status": status})
    store.write_text(
        path,
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    if rendered_aliases is not None:
        store.write_text(
            store.root / "aliases.yml",
            rendered_aliases,
        )
        _sync_model_aliases(store, target_id, alias, add=True)


def remove_alias(store: LocalStore, target_id: str, alias: str) -> None:
    alias_path = store.root / "aliases.yml"
    data = yaml.safe_load(alias_path.read_text(encoding="utf-8")) or {}
    item = data.setdefault("aliases", {}).setdefault(
        target_id,
        {"canonical_type": _target_type(store, target_id), "aliases": []},
    )
    item["aliases"] = [current for current in item.setdefault("aliases", []) if current != alias]
    store.write_text(
        alias_path,
        yaml.safe_dump(data, allow_unicode=True, sort_keys=True),
    )
    _sync_model_aliases(store, target_id, alias, add=False)


def _target_type(store: LocalStore, target_id: str) -> str:
    artifact = next(
        (item for item in store.read("artifacts", Artifact) if item.artifact_id == target_id),
        None,
    )
    if artifact:
        return artifact.artifact_type
    entity = next(
        (item for item in store.read("entities", Entity) if item.entity_id == target_id),
        None,
    )
    if entity:
        return entity.entity_type
    raise ValueError(f"Unknown alias target: {target_id}")


def set_relation_status(store: LocalStore, relation_id: str, status: str) -> None:
    if status not in {"confirmed", "unconfirmed", "rejected"}:
        raise ValueError("status must be confirmed, unconfirmed, or rejected")
    relations = store.read("relations", Relation)
    relation = next((item for item in relations if item.relation_id == relation_id), None)
    if not relation:
        raise ValueError(f"Unknown relation: {relation_id}")
    relation.status = status
    store.write("relations", relations)


def list_relations(store: LocalStore) -> str:
    return _dump([item.model_dump() for item in store.read("relations", Relation)])


def inspect_graph(store: LocalStore) -> str:
    return _dump([item.model_dump() for item in store.read("relations", Relation)])


def inspect_evidence(store: LocalStore, evidence_id: str | None = None) -> str:
    items = store.read("evidence", Evidence)
    if evidence_id:
        items = [item for item in items if item.evidence_id == evidence_id]
    return _dump([item.model_dump() for item in items])


def inspect_artifact(store: LocalStore, name: str) -> str:
    item_id = resolve_name(store, name) or name
    items = [
        item.model_dump()
        for item in [*store.read("artifacts", Artifact), *store.read("entities", Entity)]
        if getattr(item, "artifact_id", getattr(item, "entity_id", None)) == item_id
    ]
    return _dump(items)


def _dump(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _sync_model_aliases(store: LocalStore, target_id: str, alias: str, *, add: bool) -> None:
    artifacts = store.read("artifacts", Artifact)
    entities = store.read("entities", Entity)
    for item in [*artifacts, *entities]:
        item_id = getattr(item, "artifact_id", getattr(item, "entity_id", None))
        if item_id != target_id:
            continue
        if add and alias not in item.aliases:
            item.aliases.append(alias)
        if not add:
            item.aliases = [current for current in item.aliases if current != alias]
    store.write("artifacts", artifacts)
    store.write("entities", entities)
