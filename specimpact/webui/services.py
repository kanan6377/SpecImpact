from __future__ import annotations

import json
import os
import shutil
from importlib.resources import files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import yaml

from specimpact.config import load_config
from specimpact.core import (
    _build_impacts,
    _detect_changed_entities,
    analyze_change,
    explain_why,
    ingest_documents,
    latest_run_dir,
)
from specimpact.dirty_excel.ingestion import (
    decide_graph_proposal,
    ingest_dirty_excel,
    inspect_dirty_excel,
    list_graph_proposals,
)
from specimpact.dirty_excel.models import DirtyCell, DirtyRegion, DirtySheet, DirtyWorkbook
from specimpact.embeddings import rebuild_embeddings
from specimpact.graphrag import (
    configure_llm,
    disable_llm,
    is_external_llm,
    llm_status,
)
from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.decision_store import list_impacts, set_impact_status
from specimpact.impact_management.review_session import analyze_change_llm_first
from specimpact.inspection import (
    confirm_alias_candidate,
    decide_alias,
    reject_alias_candidate,
    remove_alias,
    review_alias_candidates,
    set_relation_status,
    suggest_aliases,
)
from specimpact.integrations import (
    configure_backend,
    create_baseline,
    export_obsidian,
    graph_diff,
    import_review_results,
)
from specimpact.llm_graph.schemas import AliasCandidate, GraphProposal
from specimpact.loaders import load_document
from specimpact.models import Artifact, Chunk, Document, Entity, Evidence, Relation, Section
from specimpact.operations import (
    evaluate_dataset,
    evaluate_latest,
    explain_why_not,
    privacy_doctor,
    project_status,
    release_validate,
)
from specimpact.source_freshness import (
    GraphDiffRecord,
    SourceVersion,
    StaleRecord,
    decide_graph_diff,
    resolve_stale,
)
from specimpact.store import LocalStore
from specimpact.structured_loaders import ingest_ddl, ingest_openapi
from specimpact.tabular_loaders import ingest_csv, ingest_excel
from specimpact.webui.registry import Project

MUTATING_ACTIONS = {
    "init",
    "ingest",
    "ingest_openapi",
    "ingest_ddl",
    "ingest_csv",
    "ingest_excel",
    "ingest_dirty_excel",
    "analyze",
    "analyze_text",
    "analyze_text_llm_first",
    "analyze_llm_first",
    "change_parse",
    "aliases_suggest",
    "alias_confirm",
    "alias_reject_candidate",
    "alias_decide",
    "alias_remove",
    "relation_status",
    "graph_proposal_decide",
    "impact_status",
    "llm_configure",
    "llm_disable",
    "embeddings_rebuild",
    "backend_set",
    "review_import",
    "baseline_create",
    "graph_diff",
    "graph_diff_decide",
    "obsidian_export",
    "eval",
    "release_check",
    "demo_run",
}


def store_for(project: Project) -> LocalStore:
    return LocalStore(Path(project.path) / ".specimpact")


def project_overview(project: Project) -> dict[str, Any]:
    store = store_for(project)
    initialized = (store.root / "config.yml").is_file()
    counts = _counts(store)
    latest = _latest_run_id(store)
    config = load_config(store)
    try:
        doctor = privacy_doctor(store) if initialized else "未初期化"
    except ValueError as error:
        doctor = str(error)
    return {
        "project": project.model_dump(),
        "initialized": initialized,
        "counts": counts,
        "health_check": _health_check(store),
        "dirty_excel": inspect_dirty_excel(store) if initialized else None,
        "latest_run": latest,
        "privacy_doctor": doctor,
        "llm": llm_status(store),
        "embeddings": config["embeddings"],
        "backend": config["backend"],
        "openai_api_key_available": bool(os.environ.get("OPENAI_API_KEY")),
        "codex_cli_available": bool(shutil.which("codex.cmd") or shutil.which("codex")),
    }


def graph_data(
    project: Project,
    *,
    item_type: str | None = None,
    status: str | None = None,
    extraction_method: str | None = None,
) -> dict[str, Any]:
    store = store_for(project)
    artifacts = store.read("artifacts", Artifact)
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    unresolved_stale = [
        item
        for item in store.read("stale_records", StaleRecord)
        if item.resolved_at is None
    ]
    stale_nodes = {item.target_id for item in unresolved_stale if item.target_type == "node"}
    stale_relations = {
        item.target_id for item in unresolved_stale if item.target_type == "relation"
    }
    if item_type:
        artifacts = [item for item in artifacts if item.artifact_type == item_type]
        entities = [item for item in entities if item.entity_type == item_type]
    if status:
        relations = [item for item in relations if item.status == status]
    if extraction_method:
        relations = [
            item for item in relations if item.extraction_method == extraction_method
        ]
    allowed = {
        *[item.artifact_id for item in artifacts],
        *[item.entity_id for item in entities],
    }
    if item_type:
        relations = [
            item for item in relations if item.source_id in allowed or item.target_id in allowed
        ]
    nodes = [
        {
            "data": {
                "id": item.artifact_id,
                "label": item.display_name,
                "kind": "artifact",
                "type": item.artifact_type,
                "methods": item.extraction_methods,
                "stale": item.artifact_id in stale_nodes,
            }
        }
        for item in artifacts
    ]
    nodes.extend(
        {
            "data": {
                "id": item.entity_id,
                "label": item.display_name,
                "kind": "entity",
                "type": item.entity_type,
                "methods": item.extraction_methods,
                "stale": item.entity_id in stale_nodes,
            }
        }
        for item in entities
    )
    nodes_by_id = {item["data"]["id"]: item for item in nodes}
    for relation in relations:
        for node_id in (relation.source_id, relation.target_id):
            if node_id not in nodes_by_id:
                node = {"data": {"id": node_id, "label": node_id, "kind": "reference"}}
                nodes.append(node)
                nodes_by_id[node_id] = node
    edges = [
        {
            "data": {
                "id": item.relation_id,
                "source": item.source_id,
                "target": item.target_id,
                "label": item.relation_type,
                "status": item.status,
                "method": item.extraction_method,
                "evidence_ids": item.evidence_ids,
                "stale": item.relation_id in stale_relations,
            }
        }
        for item in relations
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "artifacts": [item.model_dump() for item in artifacts],
        "entities": [item.model_dump() for item in entities],
        "relations": [item.model_dump() for item in relations],
    }


def evidence_data(
    project: Project,
    evidence_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    items = store_for(project).read("evidence", Evidence)
    if evidence_ids:
        selected = set(evidence_ids)
        items = [item for item in items if item.evidence_id in selected]
    return [item.model_dump() for item in items]


def design_documents_data(
    project: Project,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Return source-document previews with evidence-addressable highlights."""
    store = store_for(project)
    selected = set(evidence_ids or _latest_report_evidence_ids(store))
    documents = store.read("documents", Document)
    chunks = store.read("chunks", Chunk)
    evidence = store.read("evidence", Evidence)
    dirty_cells = store.read("dirty_cells", DirtyCell)
    dirty_regions = store.read("dirty_regions", DirtyRegion)

    evidence_by_file: dict[str, list[Evidence]] = {}
    for item in evidence:
        evidence_by_file.setdefault(item.source_location.file, []).append(item)
    cells_by_file: dict[str, list[DirtyCell]] = {}
    for cell in dirty_cells:
        cells_by_file.setdefault(cell.file_path, []).append(cell)
    regions_by_file: dict[str, list[DirtyRegion]] = {}
    for region in dirty_regions:
        workbook = next(
            (cell.file_path for cell in dirty_cells if cell.workbook_id == region.workbook_id),
            region.workbook_id,
        )
        regions_by_file.setdefault(workbook, []).append(region)

    by_file: dict[str, dict[str, Any]] = {}
    for document in documents:
        by_file[document.path] = {
            "document_id": document.document_id,
            "title": document.title,
            "file": document.path,
            "document_type": document.document_type,
        }
    for file_name in {*evidence_by_file, *cells_by_file, *regions_by_file}:
        by_file.setdefault(
            file_name,
            {
                "document_id": None,
                "title": Path(file_name).name,
                "file": file_name,
                "document_type": "design_document",
            },
        )

    chunk_text_by_doc: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        chunk_text_by_doc.setdefault(chunk.document_id, []).append(chunk)

    previews = []
    for file_name, base in sorted(by_file.items(), key=lambda item: item[0]):
        file_evidence = evidence_by_file.get(file_name, [])
        highlighted = [item for item in file_evidence if item.evidence_id in selected]
        doc_id = base.get("document_id")
        rows = _source_rows(project, file_name, file_evidence, selected)
        if not rows and doc_id:
            rows = _chunk_rows(chunk_text_by_doc.get(doc_id, []), file_evidence, selected)
        cells = _dirty_cell_rows(cells_by_file.get(file_name, []), selected)
        regions = [
            {
                "region_id": region.region_id,
                "sheet_name": region.sheet_name,
                "range": region.range,
                "region_type": region.region_type,
                "highlight": bool(set(region.evidence_ids) & selected),
                "evidence_ids": region.evidence_ids,
                "rendered_text": region.rendered_text[:2000],
            }
            for region in regions_by_file.get(file_name, [])
        ]
        previews.append(
            {
                **base,
                "highlight_count": len(highlighted),
                "evidence_count": len(file_evidence),
                "evidence": [_evidence_summary(item) for item in file_evidence],
                "rows": rows,
                "cells": cells,
                "regions": regions,
            }
        )

    return {
        "selected_evidence_ids": sorted(selected),
        "documents": previews,
    }


def source_library_data(project: Project) -> dict[str, Any]:
    """Summarize ingested design sources and additive freshness state."""
    store = store_for(project)
    documents = store.read("documents", Document)
    evidence = store.read("evidence", Evidence)
    artifacts = store.read("artifacts", Artifact)
    relations = store.read("relations", Relation)
    workbooks = store.read("dirty_workbooks", DirtyWorkbook)
    sheets = store.read("dirty_sheets", DirtySheet)
    regions = store.read("dirty_regions", DirtyRegion)
    versions = store.read("source_versions", SourceVersion)
    unresolved_stale = [
        item
        for item in store.read("stale_records", StaleRecord)
        if item.resolved_at is None
    ]
    versions_by_document: dict[str, list[SourceVersion]] = {}
    for version in versions:
        versions_by_document.setdefault(version.document_id, []).append(version)
    stale_by_document: dict[str, int] = {}
    for record in unresolved_stale:
        stale_by_document[record.document_id] = stale_by_document.get(record.document_id, 0) + 1

    evidence_counts: dict[str, int] = {}
    for item in evidence:
        evidence_counts[item.document_id] = evidence_counts.get(item.document_id, 0) + 1
    artifact_counts: dict[str, int] = {}
    for item in artifacts:
        for document_id in item.source_document_ids:
            artifact_counts[document_id] = artifact_counts.get(document_id, 0) + 1
    relation_counts: dict[str, int] = {}
    for item in relations:
        for document_id in item.source_document_ids:
            relation_counts[document_id] = relation_counts.get(document_id, 0) + 1

    workbook_by_path: dict[str, DirtyWorkbook] = {}
    for workbook in workbooks:
        for path in (workbook.file_path, workbook.original_path):
            workbook_by_path[_path_key(path)] = workbook
    sheet_counts: dict[str, int] = {}
    for sheet in sheets:
        sheet_counts[sheet.workbook_id] = sheet_counts.get(sheet.workbook_id, 0) + 1
    region_counts: dict[str, int] = {}
    for region in regions:
        region_counts[region.workbook_id] = region_counts.get(region.workbook_id, 0) + 1

    items: list[dict[str, Any]] = []
    represented_workbooks: set[str] = set()
    for document in documents:
        workbook = workbook_by_path.get(_path_key(document.path))
        if workbook:
            represented_workbooks.add(workbook.workbook_id)
        item_evidence = evidence_counts.get(document.document_id, 0)
        document_versions = sorted(
            versions_by_document.get(document.document_id, []),
            key=lambda item: item.version_number,
        )
        latest_version = document_versions[-1] if document_versions else None
        items.append(
            {
                "source_id": document.document_id,
                "title": document.title,
                "path": document.path,
                "source_type": document.document_type,
                "loaded_at": document.loaded_at,
                "evidence_count": item_evidence,
                "artifact_count": artifact_counts.get(document.document_id, 0),
                "relation_count": relation_counts.get(document.document_id, 0),
                "sheet_count": sheet_counts.get(workbook.workbook_id, 0) if workbook else 0,
                "region_count": region_counts.get(workbook.workbook_id, 0) if workbook else 0,
                "warnings": workbook.warnings if workbook else [],
                "status": "ready" if item_evidence else "indexed",
                "version_count": len(document_versions),
                "latest_change_type": latest_version.change_type if latest_version else None,
                "latest_change_at": latest_version.detected_at if latest_version else None,
                "stale_count": stale_by_document.get(document.document_id, 0),
            }
        )
    for workbook in workbooks:
        if workbook.workbook_id in represented_workbooks:
            continue
        items.append(
            {
                "source_id": workbook.workbook_id,
                "title": Path(workbook.file_path).name,
                "path": workbook.file_path,
                "source_type": "dirty_excel",
                "loaded_at": None,
                "evidence_count": sum(
                    1
                    for item in evidence
                    if _path_key(item.source_location.file) == _path_key(workbook.file_path)
                ),
                "artifact_count": 0,
                "relation_count": 0,
                "sheet_count": sheet_counts.get(workbook.workbook_id, 0),
                "region_count": region_counts.get(workbook.workbook_id, 0),
                "warnings": workbook.warnings,
                "status": "ready",
                "version_count": 0,
                "latest_change_type": None,
                "latest_change_at": None,
                "stale_count": 0,
            }
        )
    return {"sources": sorted(items, key=lambda item: (item["title"], item["path"]))}


def report_data(project: Project) -> dict[str, Any]:
    store = store_for(project)
    report = json.loads((latest_run_dir(store) / "report.json").read_text(encoding="utf-8"))
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    for group in ("must_review", "should_review", "may_review", "hidden"):
        for impact in report.get(group, []):
            impact["evidence"] = [
                _evidence_summary(evidence[evidence_id])
                for evidence_id in impact.get("evidence_ids", [])
                if evidence_id in evidence
            ]
    change = report.get("change", {})
    report["change"] = {
        "change_id": change.get("change_id"),
        "title": change.get("title"),
        "path": change.get("path"),
        "changed_entity_ids": change.get("changed_entity_ids", []),
    }
    return report


def run_history(project: Project) -> list[dict[str, Any]]:
    store = store_for(project)
    rows = []
    for path in sorted((store.root / "runs").glob("*/report.json"), reverse=True):
        report = json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {
                "run_id": report["run_id"],
                "title": report["change"]["title"],
                "candidate_count": sum(
                    len(report.get(name, []))
                    for name in ("must_review", "should_review", "may_review", "hidden")
                ),
            }
        )
    return rows


def aliases_data(project: Project) -> dict[str, Any]:
    store = store_for(project)
    aliases_path = store.root / "aliases.yml"
    suggestions_path = store.root / "alias_suggestions.jsonl"
    aliases = (
        yaml.safe_load(aliases_path.read_text(encoding="utf-8")) if aliases_path.exists() else {}
    )
    suggestions = (
        [
            json.loads(line)
            for line in suggestions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if suggestions_path.exists()
        else []
    )
    candidates_path = store.root / "alias_candidates.jsonl"
    candidates = (
        [
            json.loads(line)
            for line in candidates_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if candidates_path.exists()
        else []
    )
    return {"aliases": aliases or {}, "suggestions": suggestions, "candidates": candidates}


def dirty_excel_data(project: Project) -> dict[str, Any]:
    store = store_for(project)
    regions_path = store.root / "dirty_regions.jsonl"
    proposals = json.loads(list_graph_proposals(store))
    regions = (
        [
            json.loads(line)
            for line in regions_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if regions_path.exists()
        else []
    )
    return {"summary": inspect_dirty_excel(store), "regions": regions, "proposals": proposals}


def impact_decisions_data(project: Project, change_id: str | None = None) -> list[dict[str, Any]]:
    store = store_for(project)
    decisions = json.loads(list_impacts(store, change_id))
    impacts_by_id: dict[str, dict[str, Any]] = {}
    try:
        report = json.loads((latest_run_dir(store) / "report.json").read_text(encoding="utf-8"))
    except ValueError:
        report = {}
    change = report.get("change", {})
    change_id = change.get("change_id") if isinstance(change, dict) else None
    for group in ("must_review", "should_review", "may_review", "hidden"):
        for impact in report.get(group, []):
            impact_id = f"impact.{change_id}.{impact['artifact_id']}"
            impacts_by_id[impact_id] = impact
    for decision in decisions:
        impact = impacts_by_id.get(decision["impact_id"], {})
        decision.update(
            {
                "display_name": impact.get("display_name", decision["candidate_node_id"]),
                "artifact_type": impact.get("artifact_type", ""),
                "review_priority": impact.get("review_priority", ""),
                "impact_reason": impact.get("reason", ""),
                "impact_type": impact.get("impact_type", ""),
                "required_actions": impact.get("required_actions", []),
                "warnings": impact.get("warnings", []),
                "evidence_ids": impact.get("evidence_ids", []),
            }
        )
    return decisions


def review_queue_data(project: Project) -> dict[str, Any]:
    """Project existing reviewable records into one evidence-backed queue."""
    store = store_for(project)
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    unresolved_stale = [
        item
        for item in store.read("stale_records", StaleRecord)
        if item.resolved_at is None
    ]
    stale_relations = {
        item.target_id: item for item in unresolved_stale if item.target_type == "relation"
    }
    stale_impacts = {
        item.target_id: item for item in unresolved_stale if item.target_type == "impact"
    }
    items: list[dict[str, Any]] = []

    for diff in store.read("graph_diffs", GraphDiffRecord):
        items.append(
            _review_item(
                item_id=f"graph_diff:{diff.diff_id}",
                kind="graph_diff",
                record_id=diff.diff_id,
                title=f"Graph diff {diff.diff_id}",
                subtitle=f"{len(diff.document_ids)} source changes",
                status=diff.status,
                priority="should_review" if diff.status == "pending" else "may_review",
                reason=diff.reason or "再取り込みで変化したrelationを確認します。",
                evidence_ids=[],
                evidence=evidence,
                metadata={
                    "transaction_id": diff.transaction_id,
                    "document_ids": diff.document_ids,
                    "added_relation_ids": diff.added_relation_ids,
                    "removed_relation_ids": diff.removed_relation_ids,
                    "changed_relation_ids": diff.changed_relation_ids,
                    "created_at": diff.created_at,
                    "reviewed_at": diff.reviewed_at,
                },
            )
        )

    for proposal in store.read("graph_proposals", GraphProposal):
        evidence_ids = sorted(
            {
                evidence_id
                for record in [*proposal.result.nodes, *proposal.result.edges]
                for evidence_id in record.evidence_ids
            }
        )
        items.append(
            _review_item(
                item_id=f"proposal:{proposal.proposal_id}",
                kind="graph_proposal",
                record_id=proposal.proposal_id,
                title=f"Region {proposal.region_id}",
                subtitle=f"{len(proposal.result.nodes)} nodes / {len(proposal.result.edges)} edges",
                status=proposal.status,
                priority="should_review" if proposal.status == "pending" else "may_review",
                reason=(
                    "; ".join(proposal.result.warnings)
                    or "抽出nodeとedgeをgraphへ採用するか確認します。"
                ),
                evidence_ids=evidence_ids,
                evidence=evidence,
                metadata={
                    "region_id": proposal.region_id,
                    "extraction_method": proposal.extraction_method,
                    "node_count": len(proposal.result.nodes),
                    "edge_count": len(proposal.result.edges),
                    "nodes": [
                        {
                            "id": node.temp_id,
                            "type": node.node_type,
                            "name": node.display_name,
                            "rationale": node.rationale,
                        }
                        for node in proposal.result.nodes
                    ],
                    "edges": [
                        {
                            "source": edge.source_temp_id,
                            "relation": edge.relation_type,
                            "target": edge.target_temp_id,
                            "inference_level": edge.inference_level,
                            "rationale": edge.rationale,
                        }
                        for edge in proposal.result.edges
                    ],
                    "unresolved_mentions": proposal.result.unresolved_mentions,
                },
            )
        )
        for index, mention in enumerate(proposal.result.unresolved_mentions):
            items.append(
                _review_item(
                    item_id=f"mention:{proposal.proposal_id}:{index}",
                    kind="unresolved_mention",
                    record_id=proposal.proposal_id,
                    title=mention,
                    subtitle=f"Region {proposal.region_id}",
                    status="needs_investigation",
                    priority="may_review",
                    reason="別紙参照、同上、または文脈不足の参照を人間が確認してください。",
                    evidence_ids=evidence_ids,
                    evidence=evidence,
                    metadata={"region_id": proposal.region_id},
                )
            )

    for candidate in store.read("alias_candidates", AliasCandidate):
        items.append(
            _review_item(
                item_id=f"alias:{candidate.candidate_id}",
                kind="alias",
                record_id=candidate.candidate_id,
                title=candidate.entity_a_id or candidate.target_id,
                subtitle=(
                    f"{candidate.judgement}: "
                    f"{candidate.entity_b_id or ', '.join(candidate.aliases)}"
                ),
                status=candidate.status,
                priority=(
                    "should_review"
                    if candidate.status == "pending" and candidate.judgement in {"same", "related"}
                    else "may_review"
                ),
                reason=candidate.llm_reason or candidate.reason or "Alias候補の根拠を確認します。",
                evidence_ids=candidate.evidence_ids,
                evidence=evidence,
                metadata={
                    "judgement": candidate.judgement,
                    "aliases": candidate.aliases,
                    "relation_context": candidate.relation_context,
                    "surrounding_node_ids": candidate.surrounding_node_ids,
                    "evidence_quotes": candidate.evidence_quotes,
                },
            )
        )

    for relation in store.read("relations", Relation):
        stale = stale_relations.get(relation.relation_id)
        items.append(
            _review_item(
                item_id=f"relation:{relation.relation_id}",
                kind="relation",
                record_id=relation.relation_id,
                title=relation.relation_type,
                subtitle=f"{relation.source_id} → {relation.target_id}",
                status="stale" if stale else relation.status,
                priority=(
                    "should_review" if stale or relation.status == "unconfirmed" else "may_review"
                ),
                reason=(
                    f"{relation.extraction_method} / {relation.polarity} / {relation.match_type}"
                ),
                evidence_ids=relation.evidence_ids,
                evidence=evidence,
                metadata={
                    "source_id": relation.source_id,
                    "target_id": relation.target_id,
                    "extraction_method": relation.extraction_method,
                    "polarity": relation.polarity,
                    "match_type": relation.match_type,
                    "actual_status": relation.status,
                    "stale_reason": stale.reason if stale else "",
                },
            )
        )

    for decision in impact_decisions_data(project):
        stale = stale_impacts.get(decision["impact_id"])
        items.append(
            _review_item(
                item_id=f"impact:{decision['impact_id']}",
                kind="impact",
                record_id=decision["impact_id"],
                title=decision["display_name"],
                subtitle=decision.get("artifact_type", ""),
                status="stale" if stale else decision["status"],
                priority=decision.get("review_priority") or "may_review",
                reason=decision.get("impact_reason") or decision.get("reason") or "",
                evidence_ids=decision.get("evidence_ids", []),
                evidence=evidence,
                metadata={
                    "change_id": decision["change_id"],
                    "impact_type": decision.get("impact_type", ""),
                    "required_actions": decision.get("required_actions", []),
                    "warnings": decision.get("warnings", []),
                    "decision_reason": decision.get("reason", ""),
                    "updated_at": decision.get("updated_at"),
                    "actual_status": decision["status"],
                    "stale_reason": stale.reason if stale else "",
                },
            )
        )

    status_rank = {
        "pending": 0,
        "unreviewed": 0,
        "unconfirmed": 0,
        "stale": 0,
        "needs_investigation": 1,
    }
    priority_rank = {"must_review": 0, "should_review": 1, "may_review": 2}
    items.sort(
        key=lambda item: (
            status_rank.get(item["status"], 2),
            priority_rank.get(item["priority"], 3),
            item["kind"],
            item["title"],
        )
    )
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "actionable": sum(
                item["status"]
                in {"pending", "unreviewed", "unconfirmed", "needs_investigation", "stale"}
                for item in items
            ),
            "by_kind": _value_counts(item["kind"] for item in items),
            "by_status": _value_counts(item["status"] for item in items),
        },
    }


def integration_data(project: Project) -> dict[str, Any]:
    """Return safe Obsidian preview and replay/audit metadata."""
    store = store_for(project)
    try:
        run_dir = latest_run_dir(store)
    except ValueError:
        run_dir = None
    traces = _safe_audit_rows(store.root / "trace.jsonl")
    if run_dir is not None:
        traces.extend(_safe_audit_rows(run_dir / "trace.jsonl"))
    sessions_path = store.root / "review_sessions.jsonl"
    sessions = (
        [
            {
                key: row.get(key)
                for key in (
                    "run_id",
                    "change_id",
                    "llm_provider",
                    "llm_model",
                    "retrieved_count",
                    "impact_count",
                )
            }
            for row in _jsonl_rows(sessions_path)
        ]
        if sessions_path.exists()
        else []
    )
    replay = None
    if run_dir is not None and (run_dir / "review_replay.json").exists():
        raw_replay = json.loads((run_dir / "review_replay.json").read_text(encoding="utf-8"))
        replay = {
            "run_id": raw_replay.get("run_id"),
            "change_id": raw_replay.get("change_id"),
            "llm_provider": raw_replay.get("llm_provider"),
            "llm_model": raw_replay.get("llm_model"),
            "atom_count": len(raw_replay.get("atom_ids", [])),
            "retrieved_path_count": len(raw_replay.get("retrieved_paths", [])),
            "impact_count": len(raw_replay.get("impact_ids", [])),
        }
    return {
        "obsidian": {
            "default_output": str(Path(project.path) / "obsidian-vault"),
            "artifact_notes": len(store.read("artifacts", Artifact))
            + len(store.read("entities", Entity)),
            "evidence_notes": len(store.read("evidence", Evidence)),
            "impact_notes": len(json.loads(list_impacts(store))),
            "change_notes": 1 if run_dir is not None else 0,
            "canvas_files": 1 if run_dir is not None else 0,
            "layout": [
                "SpecImpact/Dashboard.md",
                "SpecImpact/Artifacts/*.md",
                "SpecImpact/Evidence/*.md",
                "SpecImpact/Changes/*.md",
                "SpecImpact/Impacts/*.md",
                "SpecImpact/Canvases/*.canvas",
            ],
        },
        "audit": {
            "llm_events": traces[-100:],
            "review_sessions": sessions[-50:],
            "latest_replay": replay,
        },
    }


def external_preview(project: Project, action: str, params: dict[str, Any]) -> dict[str, Any]:
    store = store_for(project)
    config = load_config(store)
    purposes: list[dict[str, Any]] = []
    no_llm = bool(params.get("no_llm"))
    dataset_case_count = _dataset_case_count(project, action, params)
    llm = config["llm"]
    dirty_llm = action == "ingest_dirty_excel" and bool(params.get("llm"))
    graph_llm = action in {
        "ingest",
        "analyze",
        "analyze_llm_first",
        "analyze_text_llm_first",
    } and not no_llm
    alias_llm = action == "aliases_suggest" and bool(params.get("llm", True)) and not no_llm
    if (dirty_llm or graph_llm or alias_llm) and is_external_llm(llm):
        if action == "ingest":
            purposes.append(
                {
                    "provider": llm.get("provider"),
                    "model": llm.get("model"),
                    "purpose": "文書 chunk 抽出",
                    "item_count": _ingest_chunk_count(project, params),
                }
            )
        elif action == "ingest_dirty_excel":
            purposes.append(
                {
                    "provider": llm.get("provider"),
                    "model": llm.get("model"),
                    "purpose": "Dirty Excel region extraction",
                    "item_count": 1,
                }
            )
        elif action == "aliases_suggest":
            purposes.append(
                {
                    "provider": llm.get("provider"),
                    "model": llm.get("model"),
                    "purpose": "alias resolution judgement",
                    "item_count": len(store.read("entities", Entity)),
                }
            )
        elif action == "analyze_text_llm_first":
            common = {"provider": llm.get("provider"), "model": llm.get("model")}
            purposes.extend(
                [
                    {
                        **common,
                        "purpose": "natural language change extraction",
                        "item_count": 1,
                    },
                    {
                        **common,
                        "purpose": "GraphRAG impact hypothesis generation",
                        "item_count": len(store.read("artifacts", Artifact)),
                    },
                ]
            )
        else:
            purposes.extend(_analyze_llm_transmissions(project, store, params, llm))
    if dataset_case_count and not no_llm and is_external_llm(llm):
        purposes.extend(_dataset_llm_transmissions(llm, dataset_case_count))
    embeddings = config["embeddings"]
    if dataset_case_count is not None:
        semantic_query_count = dataset_case_count or None
    else:
        semantic_query_count = 1 if action in {"analyze", "demo_run"} else None
    if semantic_query_count is not None and embeddings.get("enabled") and (
        embeddings.get("provider") == "openai"
    ):
        purposes.append(
            {
                "provider": "openai",
                "model": embeddings.get("model"),
                "purpose": "semantic query",
                "item_count": semantic_query_count,
            }
        )
    if action == "embeddings_rebuild" and params.get("provider", "local") == "openai":
        purposes.append(
            {
                "provider": "openai",
                "model": params.get("model"),
                "purpose": "embedding rebuild",
                "item_count": len(store.read("chunks", Chunk)),
            }
        )
    return {"required": bool(purposes), "transmissions": purposes}


def execute(project: Project, action: str, params: dict[str, Any]) -> dict[str, Any]:
    if action not in MUTATING_ACTIONS:
        raise ValueError(f"Unknown GUI action: {action}")
    store = store_for(project)
    approved = bool(params.get("external_approved"))

    if external_preview(project, action, params)["required"] and not approved:
        raise ValueError("External transmission approval is required for this job.")

    def confirm(_message: str) -> bool:
        return approved
    before = _counts(store)
    if action == "init":
        store.init()
        result: Any = {"message": "案件を初期化しました。"}
    elif action == "ingest":
        result = {
            "documents": ingest_documents(
                store,
                _path(project, params, "path"),
                _optional_path(project, params, "aliases"),
                yes=approved,
                no_llm=bool(params.get("no_llm")),
                confirm=confirm,
            )
        }
    elif action == "ingest_openapi":
        result = {"operations": len(ingest_openapi(store, _path(project, params, "path")))}
    elif action == "ingest_ddl":
        result = {"tables": len(ingest_ddl(store, _path(project, params, "path")))}
    elif action == "ingest_csv":
        result = {"tables": len(ingest_csv(store, _path(project, params, "path")))}
    elif action == "ingest_excel":
        result = {
            "sheets": len(
                ingest_excel(
                    store,
                    _path(project, params, "path"),
                    _optional_path(project, params, "aliases"),
                    params.get("profile"),
                )
            )
        }
    elif action == "ingest_dirty_excel":
        summary = ingest_dirty_excel(
            store,
            _path(project, params, "path"),
            _optional_path(project, params, "aliases"),
            use_llm=bool(params.get("llm")),
            yes=approved,
            confirm=confirm,
        )
        result = summary.model_dump()
    elif action == "analyze":
        report = analyze_change(
            store,
            _path(project, params, "path"),
            yes=approved,
            no_llm=bool(params.get("no_llm")),
            confirm=confirm,
        )
        result = {"run_id": report.run_id, "candidates": len(report.impacts)}
    elif action == "analyze_llm_first":
        report = analyze_change_llm_first(
            store,
            _path(project, params, "path"),
            yes=approved,
            no_llm=bool(params.get("no_llm")),
            confirm=confirm,
        )
        result = {"run_id": report.run_id, "candidates": len(report.impacts)}
    elif action == "analyze_text":
        body = str(params.get("body", "")).strip()
        if not body:
            raise ValueError("Change request text is required")
        if not body.startswith("#"):
            body = f"# GUI Change Request\n\n{body}\n"
        change_path = store.root / "gui" / "change_request.md"
        store.write_text(change_path, body)
        report = analyze_change(
            store,
            change_path,
            yes=approved,
            no_llm=True,
            confirm=confirm,
        )
        result = {"run_id": report.run_id, "candidates": len(report.impacts)}
    elif action == "analyze_text_llm_first":
        body = str(params.get("body", "")).strip()
        if not body:
            raise ValueError("Change request text is required")
        source = str(params.get("design_document", "")).strip()
        if not body.startswith("#"):
            heading = "GUI Change Request"
            body = f"# {heading}\n\n{body}\n"
        if source:
            context = _selected_design_context(store, source)
            body = f"{body.rstrip()}\n\n{context}\n"
        change_path = store.root / "gui" / "change_request.md"
        store.write_text(change_path, body)
        report = analyze_change_llm_first(
            store,
            change_path,
            yes=approved,
            no_llm=bool(params.get("no_llm")),
            confirm=confirm,
        )
        result = {"run_id": report.run_id, "candidates": len(report.impacts)}
    elif action == "change_parse":
        extraction = parse_change_atoms(store, _path(project, params, "path"))
        result = extraction.model_dump()
    elif action == "aliases_suggest":
        result = {"suggestions": suggest_aliases(store, use_llm=bool(params.get("llm", True)))}
    elif action == "alias_confirm":
        result = confirm_alias_candidate(store, params["candidate_id"]).model_dump()
    elif action == "alias_reject_candidate":
        result = reject_alias_candidate(store, params["candidate_id"]).model_dump()
    elif action == "alias_decide":
        decide_alias(store, params["target_id"], params["alias"], params["status"])
        result = {"target_id": params["target_id"], "status": params["status"]}
    elif action == "alias_remove":
        remove_alias(store, params["target_id"], params["alias"])
        result = {"target_id": params["target_id"], "removed": params["alias"]}
    elif action == "relation_status":
        set_relation_status(store, params["relation_id"], params["status"])
        resolve_stale(store, "relation", params["relation_id"])
        result = {"relation_id": params["relation_id"], "status": params["status"]}
    elif action == "graph_proposal_decide":
        result = decide_graph_proposal(store, params["proposal_id"], params["status"]).model_dump()
    elif action == "impact_status":
        result = set_impact_status(
            store,
            params["impact_id"],
            params["status"],
            params.get("reason", ""),
        ).model_dump()
        resolve_stale(store, "impact", params["impact_id"])
    elif action == "llm_configure":
        configure_llm(store, params["provider"], params["model"], params.get("base_url"))
        result = llm_status(store)
    elif action == "llm_disable":
        disable_llm(store)
        result = llm_status(store)
    elif action == "embeddings_rebuild":
        result = {
            "embeddings": rebuild_embeddings(
                store,
                provider=params.get("provider", "local"),
                model=params.get("model"),
                yes=approved,
                confirm=confirm,
            )
        }
    elif action == "backend_set":
        configure_backend(store, params["backend"], params.get("uri"))
        result = {"backend": params["backend"]}
    elif action == "review_import":
        result = {"review_results": import_review_results(store, _path(project, params, "path"))}
    elif action == "baseline_create":
        result = {"baseline": str(create_baseline(store, params["name"]))}
    elif action == "graph_diff":
        result = graph_diff(store, params["name"])
    elif action == "graph_diff_decide":
        result = decide_graph_diff(
            store,
            params["diff_id"],
            params["status"],
            params.get("reason", ""),
        ).model_dump()
    elif action == "obsidian_export":
        result = {
            "output": str(
                export_obsidian(
                    store,
                    _path(project, params, "path"),
                    report_only=bool(params.get("report_only")),
                )
            )
        }
    elif action == "eval":
        result = (
            evaluate_dataset(
                store,
                _path(project, params, "dataset"),
                yes=approved,
                no_llm=bool(params.get("no_llm")),
                confirm=confirm,
            )
            if params.get("dataset")
            else evaluate_latest(store, _path(project, params, "expected"))
        )
    elif action == "release_check":
        result = release_validate(
            store,
            _path(project, params, "dataset"),
            yes=approved,
            no_llm=bool(params.get("no_llm")),
            confirm=confirm,
        )
    elif action == "demo_run":
        result = _demo_run(project, approved=approved, confirm=confirm)
    after = _counts(store)
    return {"result": result, "count_delta": _delta(before, after), "counts": after}


def tool_result(project: Project, tool: str, params: dict[str, Any]) -> str:
    store = store_for(project)
    if tool == "why":
        return explain_why(store, params["name"])
    if tool == "why_not":
        return explain_why_not(store, params["name"])
    if tool == "status":
        return project_status(store)
    if tool == "privacy":
        return privacy_doctor(store)
    if tool == "alias_candidates":
        return review_alias_candidates(store)
    raise ValueError(f"Unknown read-only tool: {tool}")


def _demo_run(project: Project, *, approved: bool, confirm) -> dict[str, Any]:
    root = Path(project.path)
    store = store_for(project)
    store.init()
    documents = ingest_documents(
        store,
        root / "docs",
        root / "aliases.yml",
        yes=approved,
        no_llm=True,
        confirm=confirm,
    )
    report = analyze_change(
        store,
        root / "changes" / "change_credit_limit.md",
        yes=approved,
        no_llm=True,
        confirm=confirm,
    )
    return {"documents": documents, "run_id": report.run_id, "candidates": len(report.impacts)}


def demo_source() -> Traversable:
    return files("specimpact").joinpath("resources", "demo", "credit_card_enrollment")


def copy_demo(source: Traversable, target: Path) -> Path:
    if target.exists():
        raise ValueError(f"Demo workspace already exists: {target}")
    _copy_resource_tree(source, target)
    return target


def _counts(store: LocalStore) -> dict[str, int]:
    return {
        collection: len(store.read(collection, model))
        for collection, model in (
            ("documents", Document),
            ("sections", Section),
            ("chunks", Chunk),
            ("artifacts", Artifact),
            ("entities", Entity),
            ("relations", Relation),
            ("evidence", Evidence),
        )
    }


def _latest_run_id(store: LocalStore) -> str | None:
    path = store.root / "latest_run"
    return path.read_text(encoding="utf-8").strip() if path.exists() else None


def _latest_report_evidence_ids(store: LocalStore) -> list[str]:
    try:
        report = json.loads((latest_run_dir(store) / "report.json").read_text(encoding="utf-8"))
    except ValueError:
        return []
    ids: set[str] = set()
    for group in ("must_review", "should_review", "may_review"):
        for impact in report.get(group, []):
            ids.update(impact.get("evidence_ids", []))
    return sorted(ids)


def _source_rows(
    project: Project,
    file_name: str,
    evidence: list[Evidence],
    selected: set[str],
) -> list[dict[str, Any]]:
    path = _resolve_project_file(project, file_name)
    if path is None or not _looks_text(path):
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    evidence_by_line: dict[int, list[Evidence]] = {}
    for item in evidence:
        for line in range(item.source_location.line_start, item.source_location.line_end + 1):
            evidence_by_line.setdefault(line, []).append(item)
    wanted = _line_numbers_to_show(lines, evidence_by_line, selected)
    return [
        {
            "line": line_no,
            "text": lines[line_no - 1],
            "highlight": any(
                item.evidence_id in selected for item in evidence_by_line.get(line_no, [])
            ),
            "evidence_ids": [item.evidence_id for item in evidence_by_line.get(line_no, [])],
        }
        for line_no in wanted
    ]


def _chunk_rows(
    chunks: list[Chunk],
    evidence: list[Evidence],
    selected: set[str],
) -> list[dict[str, Any]]:
    evidence_by_line: dict[int, list[Evidence]] = {}
    for item in evidence:
        for line in range(item.source_location.line_start, item.source_location.line_end + 1):
            evidence_by_line.setdefault(line, []).append(item)
    rows = []
    for chunk in sorted(chunks, key=lambda item: item.line_start)[:80]:
        highlight = any(
            item.evidence_id in selected
            for line in range(chunk.line_start, chunk.line_end + 1)
            for item in evidence_by_line.get(line, [])
        )
        rows.append(
            {
                "line": chunk.line_start,
                "text": chunk.text,
                "highlight": highlight,
                "evidence_ids": sorted(
                    {
                        item.evidence_id
                        for line in range(chunk.line_start, chunk.line_end + 1)
                        for item in evidence_by_line.get(line, [])
                    }
                ),
            }
        )
    return rows


def _dirty_cell_rows(cells: list[DirtyCell], selected: set[str]) -> list[dict[str, Any]]:
    useful = [cell for cell in cells if cell.value not in (None, "")]
    highlighted = [cell for cell in useful if cell.evidence_id in selected]
    if highlighted:
        sheet_names = {cell.sheet_name for cell in highlighted}
        min_row = min(cell.row for cell in highlighted)
        max_row = max(cell.row for cell in highlighted)
        min_col = min(cell.column for cell in highlighted)
        max_col = max(cell.column for cell in highlighted)
        useful = [
            cell
            for cell in useful
            if cell.sheet_name in sheet_names
            and min_row - 4 <= cell.row <= max_row + 4
            and min_col - 3 <= cell.column <= max_col + 3
        ]
    else:
        useful = useful[:240]
    return [
        {
            "sheet_name": cell.sheet_name,
            "cell": cell.cell,
            "row": cell.row,
            "column": cell.column,
            "value": cell.value,
            "merged_range": cell.merged_range,
            "comment": cell.comment,
            "hyperlink": cell.hyperlink,
            "hidden": cell.is_hidden_row or cell.is_hidden_col,
            "highlight": cell.evidence_id in selected,
            "evidence_ids": [cell.evidence_id],
        }
        for cell in sorted(useful, key=lambda item: (item.sheet_name, item.row, item.column))[:400]
    ]


def _line_numbers_to_show(
    lines: list[str],
    evidence_by_line: dict[int, list[Evidence]],
    selected: set[str],
) -> list[int]:
    highlighted = [
        line_no
        for line_no, items in evidence_by_line.items()
        if any(item.evidence_id in selected for item in items)
    ]
    if not highlighted:
        return list(range(1, min(len(lines), 120) + 1))
    wanted: set[int] = set()
    for line_no in highlighted:
        wanted.update(range(max(1, line_no - 4), min(len(lines), line_no + 4) + 1))
    return sorted(wanted)


def _resolve_project_file(project: Project, file_name: str) -> Path | None:
    path = Path(file_name)
    candidates = [path] if path.is_absolute() else [Path(project.path) / path, path]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    return None


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def _selected_design_context(store: LocalStore, source: str) -> str:
    documents = store.read("documents", Document)
    selected = next(
        (
            item
            for item in documents
            if item.document_id == source or _path_key(item.path) == _path_key(source)
        ),
        None,
    )
    if selected is None:
        return f"## Selected Design Document\n\n- Source: {source}"
    artifacts = [
        item
        for item in store.read("artifacts", Artifact)
        if selected.document_id in item.source_document_ids
    ]
    entities = [
        item
        for item in store.read("entities", Entity)
        if selected.document_id in item.source_document_ids
    ]
    lines = [
        "## Selected Design Document",
        "",
        f"- Document ID: {selected.document_id}",
        f"- Title: {selected.title}",
        f"- Source: {selected.path}",
    ]
    if artifacts:
        artifact_names = ", ".join(item.display_name for item in artifacts[:30])
        lines.append(f"- Graph artifacts: {artifact_names}")
    if entities:
        entity_names = ", ".join(item.display_name for item in entities[:30])
        lines.append(f"- Graph entities: {entity_names}")
    return "\n".join(lines)


def _looks_text(path: Path) -> bool:
    return path.suffix.lower() in {
        ".md",
        ".txt",
        ".csv",
        ".tsv",
        ".json",
        ".jsonl",
        ".yml",
        ".yaml",
        ".sql",
        ".ddl",
        ".openapi",
    }


def _value_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _safe_audit_rows(path: Path) -> list[dict[str, Any]]:
    allowed = {
        "event",
        "provider",
        "model",
        "purpose",
        "item_count",
        "redacted",
        "source_hash",
        "chunk_id",
        "prompt_hash",
        "response_hash",
        "created_at",
    }
    return [
        {key: value for key, value in row.items() if key in allowed}
        for row in _jsonl_rows(path)
        if row.get("event") == "llm" and row.get("provider") and row.get("purpose")
    ]


def _health_check(store: LocalStore) -> dict[str, Any] | None:
    path = store.root / "health_check.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _path(project: Project, params: dict[str, Any], name: str) -> Path:
    value = params.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} path is required")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (Path(project.path) / path).resolve()


def _optional_path(project: Project, params: dict[str, Any], name: str) -> Path | None:
    return _path(project, params, name) if params.get(name) else None


def _delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in after}


def _analyze_llm_transmissions(
    project: Project,
    store: LocalStore,
    params: dict[str, Any],
    llm: dict[str, Any],
) -> list[dict[str, Any]]:
    rerank_count = _local_candidate_count(project, store, params)
    common = {"provider": llm.get("provider"), "model": llm.get("model")}
    return [
        {**common, "purpose": "変更要求からの entity 抽出", "item_count": 1},
        {
            **common,
            "purpose": "候補 batch rerank",
            "item_count": rerank_count,
            "item_count_label": f"{rerank_count} 以上（batch / 概算）",
            "note": (
                "local graph に基づく候補をまとめて精査します。"
                "entity 抽出結果と semantic retrieval "
                "により実際の候補数は増える場合があります。"
            ),
        },
    ]


def _dataset_llm_transmissions(
    llm: dict[str, Any],
    case_count: int,
) -> list[dict[str, Any]]:
    common = {"provider": llm.get("provider"), "model": llm.get("model")}
    return [
        {
            **common,
            "purpose": "dataset change ごとの entity 抽出",
            "item_count": case_count,
        },
        {
            **common,
            "purpose": "dataset candidate batch rerank",
            "item_count": None,
            "item_count_label": f"解析時に確定（対象 change: {case_count}）",
            "note": (
                "entity 抽出結果、local graph、semantic retrieval により候補数が変わるため、"
                "batch rerank の送信件数は各 change の解析時に確定します。"
            ),
        },
    ]


def _dataset_case_count(
    project: Project,
    action: str,
    params: dict[str, Any],
) -> int | None:
    if action not in {"eval", "release_check"} or not params.get("dataset"):
        return None
    manifest_path = _path(project, params, "dataset")
    if not manifest_path.is_file():
        raise ValueError(f"Dataset manifest does not exist: {manifest_path}")
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("Invalid dataset manifest YAML") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list):
        raise ValueError("Dataset manifest must contain a cases list")
    return len(manifest["cases"])


def _local_candidate_count(project: Project, store: LocalStore, params: dict[str, Any]) -> int:
    change_path = _path(project, params, "path")
    if not change_path.is_file():
        raise ValueError(f"Change request does not exist: {change_path}")
    body = change_path.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("#")),
        None,
    )
    if not title:
        raise ValueError("Change request must contain a Markdown heading")
    changed_entities = _detect_changed_entities(store, title, body)
    impacts, _rejected = _build_impacts(store, changed_entities, body="")
    return len(impacts)


def _ingest_chunk_count(project: Project, params: dict[str, Any]) -> int:
    docs_dir = _path(project, params, "path")
    if not docs_dir.is_dir():
        raise ValueError(f"Document directory does not exist: {docs_dir}")
    return sum(
        len(load_document(path, source_key=path.relative_to(docs_dir).as_posix())[2])
        for path in sorted(docs_dir.iterdir())
        if path.suffix.lower() in {".md", ".txt"}
    )


def _evidence_summary(evidence: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": evidence.evidence_id,
        "quote": evidence.quote,
        "source_location": evidence.source_location.model_dump(),
    }


def _review_item(
    *,
    item_id: str,
    kind: str,
    record_id: str,
    title: str,
    subtitle: str,
    status: str,
    priority: str,
    reason: str,
    evidence_ids: list[str],
    evidence: dict[str, Evidence],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "kind": kind,
        "record_id": record_id,
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "priority": priority,
        "reason": reason,
        "evidence_ids": evidence_ids,
        "evidence": [
            _evidence_summary(evidence[evidence_id])
            for evidence_id in evidence_ids
            if evidence_id in evidence
        ],
        "metadata": metadata,
    }


def _copy_resource_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_resource_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())
