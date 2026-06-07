from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from specimpact.config import load_config, save_config
from specimpact.core import latest_run_dir
from specimpact.impact_management.decision_store import ImpactDecision
from specimpact.models import Artifact, Entity, Evidence, Relation
from specimpact.store import LocalStore


def configure_backend(store: LocalStore, backend: str, uri: str | None = None) -> None:
    if backend not in {"local", "neo4j"}:
        raise ValueError("backend must be local or neo4j")
    if backend == "neo4j" and not uri:
        raise ValueError("neo4j backend requires --uri")
    config = load_config(store)
    config["backend"] = backend
    config.pop("neo4j_uri", None)
    if uri:
        config["neo4j_uri"] = uri
    save_config(store, config)


def export_obsidian(store: LocalStore, output_dir: Path, *, report_only: bool = False) -> Path:
    try:
        run_dir = latest_run_dir(store)
    except ValueError:
        run_dir = None
    output_dir.mkdir(parents=True, exist_ok=True)
    if report_only:
        if run_dir is None:
            raise ValueError("No analysis run exists")
        target = output_dir / f"specimpact-{run_dir.name}.md"
        shutil.copyfile(run_dir / "report.md", target)
        return target

    vault_root = output_dir / "SpecImpact"
    artifacts_dir = vault_root / "Artifacts"
    evidence_dir = vault_root / "Evidence"
    changes_dir = vault_root / "Changes"
    canvases_dir = vault_root / "Canvases"
    for directory in (artifacts_dir, evidence_dir, changes_dir, canvases_dir):
        directory.mkdir(parents=True, exist_ok=True)

    artifacts = store.read("artifacts", Artifact)
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    evidence = store.read("evidence", Evidence)
    decisions = store.read("impact_decisions", ImpactDecision)
    report = (
        json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        if run_dir is not None
        else None
    )

    nodes = [
        {
            "id": item.artifact_id,
            "type": item.artifact_type,
            "display_name": item.display_name,
            "aliases": item.aliases,
            "source_document_ids": item.source_document_ids,
            "extraction_methods": item.extraction_methods,
        }
        for item in artifacts
    ] + [
        {
            "id": item.entity_id,
            "type": item.entity_type,
            "display_name": item.display_name,
            "aliases": item.aliases,
            "source_document_ids": item.source_document_ids,
            "extraction_methods": item.extraction_methods,
        }
        for item in entities
    ]
    node_paths = {
        item["id"]: artifacts_dir
        / f"{_safe_filename(item['display_name'])} ({_short_id(item['id'])}).md"
        for item in nodes
    }
    evidence_paths = {
        item.evidence_id: evidence_dir / f"{_safe_filename(item.evidence_id)}.md"
        for item in evidence
    }
    decisions_by_candidate = {item.candidate_node_id: item for item in decisions}

    for node in nodes:
        outgoing = [item for item in relations if item.source_id == node["id"]]
        incoming = [item for item in relations if item.target_id == node["id"]]
        decision = decisions_by_candidate.get(node["id"])
        body = [
            "---",
            f"specimpact_id: {json.dumps(node['id'], ensure_ascii=False)}",
            f"type: {json.dumps(node['type'], ensure_ascii=False)}",
            f"review_status: {json.dumps(decision.status if decision else 'unreviewed')}",
            "---",
            "",
            f"# {node['display_name']}",
            "",
            "## Outgoing Relations",
            *[
                f"- `{relation.relation_type}` -> {_node_link(node_paths, relation.target_id)}"
                f" (`{relation.status}`)"
                for relation in outgoing
            ],
            "",
            "## Incoming Relations",
            *[
                f"- {_node_link(node_paths, relation.source_id)} -> `{relation.relation_type}`"
                f" (`{relation.status}`)"
                for relation in incoming
            ],
            "",
            "## Evidence",
            *[
                f"- {_evidence_link(evidence_paths, evidence_id)}"
                for relation in outgoing + incoming
                for evidence_id in relation.evidence_ids
                if evidence_id in evidence_paths
            ],
            "",
            "## Aliases",
            *[f"- {alias}" for alias in node["aliases"]],
        ]
        store.write_text(node_paths[node["id"]], "\n".join(body) + "\n")

    for item in evidence:
        body = [
            "---",
            f"specimpact_id: {json.dumps(item.evidence_id, ensure_ascii=False)}",
            f"document_id: {json.dumps(item.document_id, ensure_ascii=False)}",
            f"file: {json.dumps(item.source_location.file, ensure_ascii=False)}",
            f"line_start: {item.source_location.line_start}",
            f"line_end: {item.source_location.line_end}",
            "---",
            "",
            f"# {item.evidence_id}",
            "",
            "## Source",
            "",
            f"- File: `{item.source_location.file}`",
            f"- Lines: `{item.source_location.line_start}-{item.source_location.line_end}`",
            "- VS Code: "
            f"{_vscode_link(item.source_location.file, item.source_location.line_start)}",
            "",
            "## Quote",
            "",
            "```text",
            item.quote,
            "```",
        ]
        store.write_text(evidence_paths[item.evidence_id], "\n".join(body) + "\n")

    change_path = None
    canvas_path = None
    if report is not None:
        change = report["change"]
        change_path = (
            changes_dir
            / f"{_safe_filename(change['title'])} ({_short_id(change['change_id'])}).md"
        )
        change_body = [
            "---",
            f"specimpact_id: {json.dumps(change['change_id'], ensure_ascii=False)}",
            f"run_id: {json.dumps(report['run_id'])}",
            "---",
            "",
            f"# {change['title']}",
            "",
            "## Must Review",
            *_impact_lines(report.get("must_review", []), node_paths),
            "",
            "## Should Review",
            *_impact_lines(report.get("should_review", []), node_paths),
            "",
            "## May Review",
            *_impact_lines(report.get("may_review", []), node_paths),
        ]
        store.write_text(change_path, "\n".join(change_body) + "\n")
        shutil.copyfile(run_dir / "report.md", vault_root / f"Latest Report {run_dir.name}.md")
        canvas_path = (
            canvases_dir
            / f"{_safe_filename(change['title'])} ({_short_id(change['change_id'])}).canvas"
        )
        store.write_json(canvas_path, _change_canvas(output_dir, change_path, report, node_paths))
    dashboard = vault_root / "Dashboard.md"
    latest_lines = (
        [
            f"- Latest run: `{report['run_id']}`",
            "- Latest change: "
            f"{_wiki_link(_relative_to(output_dir, change_path), report['change']['title'])}",
            "- Impact canvas: "
            f"{_wiki_link(_relative_to(output_dir, canvas_path), 'Impact Canvas')}",
        ]
        if report is not None and change_path is not None and canvas_path is not None
        else [
            "- Latest run: not created yet",
            "- Next: analyze a change request to generate impact canvases",
        ]
    )
    store.write_text(
        dashboard,
        "\n".join(
            [
                "# SpecImpact Dashboard",
                "",
                *latest_lines,
                "",
                "## Review Queues",
                "",
                "```dataview",
                'TABLE type, review_status FROM "SpecImpact/Artifacts"',
                "WHERE review_status != \"closed\"",
                "SORT review_status ASC",
                "```",
            ]
        )
        + "\n",
    )
    return dashboard


def import_review_results(store: LocalStore, path: Path) -> int:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("review result file must contain a JSON list")
    target = store.root / "review_results.jsonl"
    store.write_text(
        target,
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    return len(rows)


def create_baseline(store: LocalStore, name: str) -> Path:
    target = store.root / "baselines" / f"{name}.relations.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(store.root / "relations.jsonl", target)
    return target


def graph_diff(store: LocalStore, name: str) -> dict[str, list[str]]:
    baseline_path = store.root / "baselines" / f"{name}.relations.jsonl"
    baseline = {
        Relation.model_validate_json(line).relation_id
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    current = {item.relation_id for item in store.read("relations", Relation)}
    return {"added": sorted(current - baseline), "removed": sorted(baseline - current)}


def export_neo4j_cypher(store: LocalStore, output_path: Path) -> Path:
    artifacts = store.read("artifacts", Artifact)
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    evidence = store.read("evidence", Evidence)
    decisions = store.read("impact_decisions", ImpactDecision)
    lines = [
        "// SpecImpact Evidence Graph / Domain Graph / Impact Graph export",
        "CREATE CONSTRAINT specimpact_node_id IF NOT EXISTS "
        "FOR (n:SpecImpactNode) REQUIRE n.id IS UNIQUE;",
        "CREATE CONSTRAINT specimpact_evidence_id IF NOT EXISTS "
        "FOR (e:Evidence) REQUIRE e.id IS UNIQUE;",
    ]
    for artifact in artifacts:
        lines.append(
            f"MERGE (n:SpecImpactNode:Artifact {{id: {_cypher(artifact.artifact_id)}}}) "
            f"SET n.name={_cypher(artifact.display_name)}, "
            f"n.type={_cypher(artifact.artifact_type)};"
        )
    for entity in entities:
        lines.append(
            f"MERGE (n:SpecImpactNode:Entity {{id: {_cypher(entity.entity_id)}}}) "
            f"SET n.name={_cypher(entity.display_name)}, "
            f"n.type={_cypher(entity.entity_type)};"
        )
    for item in evidence:
        lines.append(
            f"MERGE (e:Evidence {{id: {_cypher(item.evidence_id)}}}) "
            f"SET e.file={_cypher(item.source_location.file)}, "
            f"e.line_start={item.source_location.line_start}, "
            f"e.line_end={item.source_location.line_end};"
        )
    for relation in relations:
        rel_type = re.sub(r"[^A-Z0-9_]", "_", relation.relation_type.upper()) or "RELATED"
        lines.append(
            f"MATCH (s:SpecImpactNode {{id: {_cypher(relation.source_id)}}}), "
            f"(t:SpecImpactNode {{id: {_cypher(relation.target_id)}}}) "
            f"MERGE (s)-[r:{rel_type} {{id: {_cypher(relation.relation_id)}}}]->(t) "
            f"SET r.status={_cypher(relation.status)}, r.layer='domain';"
        )
        for evidence_id in relation.evidence_ids:
            lines.append(
                f"MATCH (s:SpecImpactNode {{id: {_cypher(relation.source_id)}}}), "
                f"(e:Evidence {{id: {_cypher(evidence_id)}}}) "
                f"MERGE (s)-[:HAS_EVIDENCE {{relation_id: {_cypher(relation.relation_id)}}}]->(e);"
            )
    for decision in decisions:
        lines.append(
            f"MATCH (n:SpecImpactNode {{id: {_cypher(decision.candidate_node_id)}}}) "
            f"MERGE (i:ImpactDecision {{id: {_cypher(decision.impact_id)}}}) "
            f"SET i.change_id={_cypher(decision.change_id)}, i.status={_cypher(decision.status)}, "
            f"i.reason={_cypher(decision.reason)} MERGE (i)-[:REVIEWS]->(n);"
        )
    store.write_text(output_path, "\n".join(lines) + "\n")
    return output_path


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return cleaned[:80] or "untitled"


def _short_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:32] or "id"


def _relative_to(root: Path, path: Path) -> Path:
    return path.resolve().relative_to(root.resolve())


def _wiki_link(path: Path, alias: str) -> str:
    return f"[[{path.with_suffix('').as_posix()}|{alias}]]"


def _vscode_link(file: str, line: int) -> str:
    return f"vscode://file/{Path(file).as_posix()}:{line}"


def _cypher(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _node_link(paths: dict[str, Path], node_id: str) -> str:
    path = paths.get(node_id)
    if not path:
        return f"`{node_id}`"
    return _wiki_link(Path("SpecImpact") / "Artifacts" / path.name, path.stem)


def _evidence_link(paths: dict[str, Path], evidence_id: str) -> str:
    path = paths.get(evidence_id)
    if not path:
        return f"`{evidence_id}`"
    return _wiki_link(Path("SpecImpact") / "Evidence" / path.name, evidence_id)


def _impact_lines(impacts: list[dict[str, object]], node_paths: dict[str, Path]) -> list[str]:
    return [
        f"- {_node_link(node_paths, str(item['artifact_id']))}: {item.get('reason', '')}"
        for item in impacts
    ]


def _change_canvas(
    vault_root: Path,
    change_path: Path,
    report: dict[str, object],
    node_paths: dict[str, Path],
) -> dict[str, object]:
    canvas_nodes = [
        {
            "id": "change",
            "type": "file",
            "file": _relative_to(vault_root, change_path).as_posix(),
            "x": 0,
            "y": 0,
            "width": 360,
            "height": 160,
        }
    ]
    canvas_edges = []
    visible = [
        *(report.get("must_review", []) or []),
        *(report.get("should_review", []) or []),
        *(report.get("may_review", []) or []),
    ]
    for index, impact in enumerate(visible):
        artifact_id = str(impact["artifact_id"])
        path = node_paths.get(artifact_id)
        if not path:
            continue
        node_id = f"impact-{index}"
        canvas_nodes.append(
            {
                "id": node_id,
                "type": "file",
                "file": (Path("SpecImpact") / "Artifacts" / path.name).as_posix(),
                "x": 460,
                "y": index * 190,
                "width": 360,
                "height": 150,
            }
        )
        canvas_edges.append(
            {
                "id": f"edge-{index}",
                "fromNode": "change",
                "toNode": node_id,
                "label": str(impact.get("review_priority", "review")),
            }
        )
    return {"nodes": canvas_nodes, "edges": canvas_edges}
