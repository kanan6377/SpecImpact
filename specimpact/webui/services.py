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
    return json.loads(list_impacts(store_for(project), change_id))


def external_preview(project: Project, action: str, params: dict[str, Any]) -> dict[str, Any]:
    store = store_for(project)
    config = load_config(store)
    purposes: list[dict[str, Any]] = []
    no_llm = bool(params.get("no_llm"))
    dataset_case_count = _dataset_case_count(project, action, params)
    llm = config["llm"]
    dirty_llm = action == "ingest_dirty_excel" and bool(params.get("llm"))
    graph_llm = action in {"ingest", "analyze", "analyze_llm_first"} and not no_llm
    if (dirty_llm or graph_llm) and is_external_llm(llm):
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
        report = analyze_change_llm_first(store, _path(project, params, "path"))
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
    elif action == "change_parse":
        extraction = parse_change_atoms(store, _path(project, params, "path"))
        result = extraction.model_dump()
    elif action == "aliases_suggest":
        result = {"suggestions": suggest_aliases(store, use_llm=bool(params.get("llm")))}
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
    elif action == "obsidian_export":
        result = {"output": str(export_obsidian(store, _path(project, params, "path")))}
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


def _copy_resource_tree(source: Traversable, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir():
            _copy_resource_tree(item, destination)
        else:
            destination.write_bytes(item.read_bytes())
