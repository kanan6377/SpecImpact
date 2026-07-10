from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from specimpact.models import Artifact, Document, Entity, Evidence, Relation, utc_now


class SourceVersion(BaseModel):
    version_id: str
    document_id: str
    source_path: str
    version_number: int
    content_hash: str | None = None
    previous_hash: str | None = None
    change_type: Literal["added", "modified", "removed"]
    graph_diff_id: str
    detected_at: str = Field(default_factory=utc_now)


class GraphDiffRecord(BaseModel):
    diff_id: str
    transaction_id: str
    document_ids: list[str]
    added_relation_ids: list[str] = Field(default_factory=list)
    removed_relation_ids: list[str] = Field(default_factory=list)
    changed_relation_ids: list[str] = Field(default_factory=list)
    status: Literal["pending", "reviewed", "ignored"] = "pending"
    reason: str = ""
    created_at: str = Field(default_factory=utc_now)
    reviewed_at: str | None = None


class StaleRecord(BaseModel):
    stale_id: str
    target_type: Literal["evidence", "relation", "impact", "node"]
    target_id: str
    document_id: str
    previous_hash: str | None = None
    current_hash: str | None = None
    reason: str
    detected_at: str = Field(default_factory=utc_now)
    resolved_at: str | None = None


@dataclass
class MergeFreshnessContext:
    transaction_id: str
    changes: list[dict[str, Any]]
    stale_records: list[StaleRecord]
    old_relations: dict[str, dict[str, Any]]
    stale_document_ids: set[str]


def prepare_graph_merge(
    store,
    documents: list[Document],
    prune_document_ids: set[str],
) -> MergeFreshnessContext:
    old_documents = {item.document_id: item for item in store.read("documents", Document)}
    incoming = {item.document_id: item for item in documents}
    changes: list[dict[str, Any]] = []
    for document_id, document in incoming.items():
        previous = old_documents.get(document_id)
        if previous is None:
            changes.append(_change(document, None, "added"))
        elif previous.hash != document.hash:
            changes.append(_change(document, previous.hash, "modified"))
    for document_id in prune_document_ids:
        previous = old_documents.get(document_id)
        if previous:
            changes.append(
                {
                    "document_id": document_id,
                    "source_path": previous.path,
                    "previous_hash": previous.hash,
                    "current_hash": None,
                    "change_type": "removed",
                }
            )

    stale_changes = {
        item["document_id"]: item for item in changes if item["change_type"] != "added"
    }
    stale_document_ids = set(stale_changes)
    stale_records: list[StaleRecord] = []
    for evidence in store.read("evidence", Evidence):
        if evidence.document_id in stale_document_ids:
            stale_records.append(
                _stale("evidence", evidence.evidence_id, stale_changes[evidence.document_id])
            )
    for relation in store.read("relations", Relation):
        document_id = next(
            (item for item in relation.source_document_ids if item in stale_document_ids),
            None,
        )
        if document_id:
            stale_records.append(
                _stale("relation", relation.relation_id, stale_changes[document_id])
            )
    for node in [
        *store.read("artifacts", Artifact),
        *store.read("entities", Entity),
    ]:
        document_id = next(
            (item for item in node.source_document_ids if item in stale_document_ids),
            None,
        )
        if document_id:
            node_id = getattr(node, "artifact_id", getattr(node, "entity_id", ""))
            stale_records.append(_stale("node", node_id, stale_changes[document_id]))
    stale_evidence_ids = {
        item.target_id for item in stale_records if item.target_type == "evidence"
    }
    stale_records.extend(_stale_impacts(store, stale_evidence_ids, stale_changes))
    old_relations = {
        item.relation_id: _relation_signature(item)
        for item in store.read("relations", Relation)
    }
    return MergeFreshnessContext(
        transaction_id=f"merge.{uuid4().hex}",
        changes=changes,
        stale_records=stale_records,
        old_relations=old_relations,
        stale_document_ids=stale_document_ids,
    )


def finalize_graph_merge(store, context: MergeFreshnessContext) -> GraphDiffRecord | None:
    new_relations = {
        item.relation_id: _relation_signature(item)
        for item in store.read("relations", Relation)
    }
    old_ids = set(context.old_relations)
    new_ids = set(new_relations)
    changed_ids = sorted(
        relation_id
        for relation_id in old_ids & new_ids
        if context.old_relations[relation_id] != new_relations[relation_id]
    )
    if not context.changes and old_ids == new_ids and not changed_ids:
        return None
    diff_id = f"diff.{hashlib.sha1(context.transaction_id.encode()).hexdigest()[:12]}"
    initial_load = bool(context.changes) and not old_ids and all(
        item["change_type"] == "added" for item in context.changes
    )
    diff = GraphDiffRecord(
        diff_id=diff_id,
        transaction_id=context.transaction_id,
        document_ids=sorted(item["document_id"] for item in context.changes),
        added_relation_ids=sorted(new_ids - old_ids),
        removed_relation_ids=sorted(old_ids - new_ids),
        changed_relation_ids=changed_ids,
        status="reviewed" if initial_load else "pending",
        reason="Initial graph build" if initial_load else "",
        reviewed_at=utc_now() if initial_load else None,
    )
    diffs = store.read("graph_diffs", GraphDiffRecord)
    diffs.append(diff)
    store.write("graph_diffs", diffs)
    _append_versions(store, context.changes, diff_id)
    _append_stale_records(store, context.stale_records)
    return diff


def decide_graph_diff(store, diff_id: str, status: str, reason: str = "") -> GraphDiffRecord:
    if status not in {"reviewed", "ignored"}:
        raise ValueError("status must be reviewed or ignored")
    diffs = store.read("graph_diffs", GraphDiffRecord)
    diff = next((item for item in diffs if item.diff_id == diff_id), None)
    if diff is None:
        raise ValueError(f"Unknown graph diff: {diff_id}")
    diff.status = status  # type: ignore[assignment]
    diff.reason = reason
    diff.reviewed_at = utc_now()
    store.write("graph_diffs", diffs)
    return diff


def resolve_stale(store, target_type: str, target_id: str) -> int:
    records = store.read("stale_records", StaleRecord)
    resolved = 0
    for record in records:
        if (
            record.target_type == target_type
            and record.target_id == target_id
            and record.resolved_at is None
        ):
            record.resolved_at = utc_now()
            resolved += 1
    if resolved:
        store.write("stale_records", records)
    return resolved


def freshness_data(store) -> dict[str, Any]:
    versions = store.read("source_versions", SourceVersion)
    diffs = store.read("graph_diffs", GraphDiffRecord)
    stale = store.read("stale_records", StaleRecord)
    return {
        "versions": [item.model_dump() for item in versions],
        "graph_diffs": [item.model_dump() for item in diffs],
        "stale_records": [item.model_dump() for item in stale],
        "summary": {
            "versions": len(versions),
            "pending_graph_diffs": sum(item.status == "pending" for item in diffs),
            "unresolved_stale": sum(item.resolved_at is None for item in stale),
        },
    }


def _change(document: Document, previous_hash: str | None, change_type: str) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "source_path": document.path,
        "previous_hash": previous_hash,
        "current_hash": document.hash,
        "change_type": change_type,
    }


def _stale(target_type: str, target_id: str, change: dict[str, Any]) -> StaleRecord:
    key = f"{target_type}|{target_id}|{change['document_id']}|{change['current_hash']}"
    return StaleRecord(
        stale_id=f"stale.{hashlib.sha1(key.encode()).hexdigest()[:16]}",
        target_type=target_type,  # type: ignore[arg-type]
        target_id=target_id,
        document_id=change["document_id"],
        previous_hash=change["previous_hash"],
        current_hash=change["current_hash"],
        reason=f"Source {change['change_type']}: {change['source_path']}",
    )


def _stale_impacts(
    store,
    stale_evidence_ids: set[str],
    changes: dict[str, dict[str, Any]],
) -> list[StaleRecord]:
    if not stale_evidence_ids:
        return []
    latest = store.root / "latest_run"
    if not latest.exists():
        return []
    report_path = store.root / "runs" / latest.read_text(encoding="utf-8").strip() / "report.json"
    if not report_path.exists():
        return []
    report = json.loads(report_path.read_text(encoding="utf-8"))
    change_id = str(report.get("change", {}).get("change_id", "change.unknown"))
    default_change = next(iter(changes.values()))
    records = []
    for group in ("must_review", "should_review", "may_review", "hidden"):
        for impact in report.get(group, []):
            if not (set(impact.get("evidence_ids", [])) & stale_evidence_ids):
                continue
            impact_id = f"impact.{change_id}.{impact['artifact_id']}"
            records.append(_stale("impact", impact_id, default_change))
    return records


def _relation_signature(relation: Relation) -> dict[str, Any]:
    value = relation.model_dump()
    value.pop("status", None)
    return value


def _append_versions(store, changes: list[dict[str, Any]], diff_id: str) -> None:
    versions = store.read("source_versions", SourceVersion)
    counts: dict[str, int] = {}
    for version in versions:
        counts[version.document_id] = max(
            counts.get(version.document_id, 0), version.version_number
        )
    for change in changes:
        document_id = change["document_id"]
        counts[document_id] = counts.get(document_id, 0) + 1
        key = f"{document_id}|{counts[document_id]}|{change['current_hash']}"
        versions.append(
            SourceVersion(
                version_id=f"version.{hashlib.sha1(key.encode()).hexdigest()[:16]}",
                document_id=document_id,
                source_path=change["source_path"],
                version_number=counts[document_id],
                content_hash=change["current_hash"],
                previous_hash=change["previous_hash"],
                change_type=change["change_type"],
                graph_diff_id=diff_id,
            )
        )
    store.write("source_versions", versions)


def _append_stale_records(store, incoming: list[StaleRecord]) -> None:
    if not incoming:
        return
    records = store.read("stale_records", StaleRecord)
    incoming_documents = {item.document_id for item in incoming}
    now = utc_now()
    for record in records:
        if record.document_id in incoming_documents and record.resolved_at is None:
            record.resolved_at = now
    existing_ids = {item.stale_id for item in records}
    records.extend(item for item in incoming if item.stale_id not in existing_ids)
    store.write("stale_records", records)
