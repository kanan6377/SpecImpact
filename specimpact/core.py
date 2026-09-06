from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from specimpact.config import load_config
from specimpact.embeddings import EmbeddingClient, semantic_search
from specimpact.extraction import AliasCatalog, GraphRecords, extract_markdown
from specimpact.graphrag import (
    FakeLLMClient as FakeLLMClient,
)
from specimpact.graphrag import (
    LLMClient,
    append_trace,
    client_from_config,
    ensure_llm_consent,
    extract_changed_entities,
    extract_graph_with_llm,
    rerank_batch,
)
from specimpact.loaders import load_document
from specimpact.models import (
    Artifact,
    ChangeRequest,
    Chunk,
    Entity,
    Evidence,
    Impact,
    Relation,
    Report,
)
from specimpact.schema_validation import validate_report
from specimpact.store import LocalStore

ENTITY_ID = "entity.application.requested_credit_limit"
PRIORITY_ORDER = {"must_review": 0, "should_review": 1, "may_review": 2, "hidden": 3}
MUST_RELATIONS = {"DEFINES", "WRITES", "VALIDATES", "SENDS", "REQUEST_FIELD"}
SHOULD_RELATIONS = {"READS", "DISPLAYS", "RESPONSE_FIELD", "COVERS", "CALLS"}
RERANK_BATCH_SIZE = 20


class AmbiguousAliasError(ValueError):
    def __init__(self, name: str, candidates: list[str]) -> None:
        self.name = name
        self.candidates = sorted(candidates)
        super().__init__(f'Ambiguous alias "{name}". Candidates: {", ".join(self.candidates)}')


def load_aliases(path: Path) -> dict[str, list[str]]:
    catalog = AliasCatalog.load(path)
    return {item_id: catalog.aliases_for(item_id) for item_id in catalog.entries}


def ingest_documents(
    store: LocalStore,
    docs_dir: Path,
    aliases_path: Path | None = None,
    *,
    no_llm: bool = False,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    llm_client: LLMClient | None = None,
) -> int:
    if not docs_dir.is_dir():
        raise ValueError(f"Document directory does not exist: {docs_dir}")
    store.init()
    if aliases_path:
        if not aliases_path.is_file():
            raise ValueError(f"Aliases file does not exist: {aliases_path}")
        new_aliases = aliases_path.read_text(encoding="utf-8")
        aliases = AliasCatalog.parse(new_aliases, aliases_path)
    else:
        new_aliases = None
        aliases = AliasCatalog.load(store.root / "aliases.yml")
    root_id = f"root.{hashlib.sha1(docs_dir.resolve().as_posix().encode()).hexdigest()[:12]}"
    graph = GraphRecords()
    seen_document_ids: set[str] = set()
    for path in sorted(docs_dir.iterdir()):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        document, sections, chunks = load_document(
            path, source_key=path.relative_to(docs_dir).as_posix()
        )
        if document.document_id in seen_document_ids:
            raise ValueError(f"Duplicate document ID: {document.document_id}")
        seen_document_ids.add(document.document_id)
        graph.extend(extract_markdown(document, sections, chunks, aliases))
    client = None if no_llm else llm_client or client_from_config(store)
    llm_trace: list[dict[str, object]] = []
    if client:
        ensure_llm_consent(
            client,
            purpose="ingest_extraction",
            chunk_count=len(graph.chunks),
            yes=yes,
            confirm=confirm,
        )
        llm_graph, llm_trace = extract_graph_with_llm(store, graph, aliases, client)
        graph.extend(llm_graph)
    current_ids = {item.document_id for item in graph.documents}
    prune_document_ids, manifests = store.prepare_source_manifest(root_id, current_ids)
    store.merge_graph(**graph.__dict__, prune_document_ids=prune_document_ids)
    if new_aliases is not None:
        store.write_text(store.root / "aliases.yml", new_aliases)
    store.write_source_manifests(manifests)
    append_trace(store, llm_trace)
    return len(graph.documents)


def analyze_change(
    store: LocalStore,
    change_path: Path,
    *,
    no_llm: bool = False,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    llm_client: LLMClient | None = None,
    embedding_client: EmbeddingClient | None = None,
) -> Report:
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
    client = None if no_llm else llm_client or client_from_config(store)
    llm_trace: list[dict[str, object]] = []
    suggestions: list[dict[str, str]] = []
    if client:
        ensure_llm_consent(
            client,
            purpose="change_extraction",
            chunk_count=1,
            yes=yes,
            confirm=confirm,
        )
        extracted, suggestions, trace = extract_changed_entities(store, body, client)
        changed_entities = sorted({*changed_entities, *extracted})
        llm_trace.append(trace)
    change = ChangeRequest(
        change_id=f"change.{change_path.stem}",
        title=title,
        path=change_path.as_posix(),
        body=body,
        changed_entity_ids=changed_entities,
    )
    impacts, rejected = _build_impacts(
        store,
        changed_entities,
        body,
        embedding_client,
        yes=yes,
        confirm=confirm,
    )
    if client and impacts:
        ensure_llm_consent(
            client,
            purpose="rerank_batch",
            chunk_count=len(impacts),
            yes=yes,
            confirm=confirm,
        )
        llm_trace.extend(_rerank_impacts(store, body, impacts, client))
    run_id = uuid4().hex[:12]
    from specimpact.semantic.service import markdown_summary, record_analysis

    impacts, semantic = record_analysis(store, change, run_id, impacts)
    report = Report(run_id=run_id, change=change, impacts=impacts)
    run_dir = store.root / "runs" / run_id
    store.write_json(run_dir / "change_request.json", change.model_dump())
    store.write_text(
        run_dir / "candidates.jsonl",
        "".join(
            json.dumps(impact.model_dump(exclude_none=True), ensure_ascii=False) + "\n"
            for impact in impacts
        ),
    )
    store.write_json(run_dir / "impacts.json", report.grouped())
    report_json = {"run_id": run_id, "change": change.model_dump(), **report.grouped()}
    validate_report(report_json)
    store.write_json(run_dir / "report.json", report_json)
    store.write_text(
        run_dir / "report.md", render_markdown(report, store) + markdown_summary(semantic)
    )
    _write_trace(store, run_dir, changed_entities, impacts, rejected, suggestions, llm_trace)
    from specimpact.impact_management.decision_store import ensure_decisions_for_report

    ensure_decisions_for_report(
        store, change.change_id, [impact.artifact_id for impact in impacts], semantic.analysis_id
    )
    store.write_text(store.root / "latest_run", run_id)
    return report


def _build_impacts(
    store: LocalStore,
    changed_entities: list[str],
    body: str = "",
    embedding_client: EmbeddingClient | None = None,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> tuple[list[Impact], dict[str, list[str]]]:
    entities = {item.entity_id: item for item in store.read("entities", Entity)}
    artifacts = {item.artifact_id: item for item in store.read("artifacts", Artifact)}
    relations = store.read("relations", Relation)
    impacts: dict[str, Impact] = {}
    rejected: dict[str, list[str]] = {}
    for entity_id in changed_entities:
        if entity_id not in entities:
            continue
        entity = entities[entity_id]
        llm_only = _is_llm_only(entity) and not any(
            relation.target_id == entity_id and relation.status == "confirmed"
            for relation in relations
        )
        impacts[entity_id] = Impact(
            artifact_id=entity_id,
            display_name=entity.display_name,
            artifact_type=entity.entity_type,
            review_priority="must_review",
            evidence_strength="strong",
            match_type="exact",
            relation_distance=0,
            rule_assessment="direct_match",
            reason=f"変更依頼が {entity.display_name} を直接参照しているため。",
            relation_paths=[f"change -> {entity_id}"],
            evidence_ids=[],
            relation_statuses=[],
            needs_review=True,
        )
        if llm_only:
            impacts[entity_id].review_priority = "may_review"
            impacts[entity_id].evidence_strength = "weak"
            impacts[entity_id].match_type = "semantic"
            impacts[entity_id].rule_assessment = "inferred_relation"
            impacts[entity_id].reason = "An unconfirmed LLM-only entity was matched."
    for relation in relations:
        if relation.target_id not in changed_entities or relation.source_id not in artifacts:
            continue
        if relation.status == "rejected":
            rejected.setdefault(relation.source_id, []).append(relation.relation_id)
            continue
        artifact = artifacts[relation.source_id]
        candidate = _impact_from_relation(artifact, relation)
        if artifact.artifact_id in impacts:
            _merge_impact(impacts[artifact.artifact_id], candidate)
        else:
            impacts[artifact.artifact_id] = candidate
    direct_artifact_ids = set(impacts)
    if load_config(store)["retrieval"]["graph_max_hops"] >= 2:
        for relation in relations:
            if relation.status == "rejected" or relation.source_id not in artifacts:
                continue
            if relation.target_id not in direct_artifact_ids:
                continue
            artifact = artifacts[relation.source_id]
            candidate = _impact_from_path(artifact, relation, impacts[relation.target_id])
            if artifact.artifact_id in impacts:
                _merge_impact(impacts[artifact.artifact_id], candidate)
            else:
                impacts[artifact.artifact_id] = candidate
    for candidate in _semantic_impacts(store, body, embedding_client, yes=yes, confirm=confirm):
        if candidate.artifact_id in impacts:
            _merge_impact(impacts[candidate.artifact_id], candidate)
        else:
            impacts[candidate.artifact_id] = candidate
    return sorted(
        impacts.values(), key=lambda item: (PRIORITY_ORDER[item.review_priority], item.artifact_id)
    ), rejected


def _impact_from_relation(artifact: Artifact, relation: Relation) -> Impact:
    priority = _priority_for(relation)
    assessment = (
        "alias_mention"
        if relation.relation_type == "MENTIONS"
        else "inferred_relation"
        if relation.polarity == "inferred"
        else "explicit_relation"
    )
    strength = (
        "weak" if priority == "may_review" else "strong" if priority == "must_review" else "medium"
    )
    return Impact(
        artifact_id=artifact.artifact_id,
        display_name=artifact.display_name,
        artifact_type=artifact.artifact_type,
        review_priority=priority,
        evidence_strength=strength,
        match_type=relation.match_type,
        relation_distance=1,
        rule_assessment=assessment,
        reason=f"{relation.relation_type} relation with explicit local evidence was found.",
        relation_paths=[
            f"change -> {relation.target_id} <- {relation.relation_type} - {artifact.artifact_id}"
        ],
        evidence_ids=relation.evidence_ids,
        relation_statuses=[relation.status],
        needs_review=priority != "hidden",
    )


def _merge_impact(current: Impact, incoming: Impact) -> None:
    if PRIORITY_ORDER[incoming.review_priority] < PRIORITY_ORDER[current.review_priority]:
        current.review_priority = incoming.review_priority
        current.evidence_strength = incoming.evidence_strength
        current.rule_assessment = incoming.rule_assessment
    current.relation_paths = sorted({*current.relation_paths, *incoming.relation_paths})
    current.evidence_ids = sorted({*current.evidence_ids, *incoming.evidence_ids})
    current.relation_statuses = sorted({*current.relation_statuses, *incoming.relation_statuses})
    if current.match_type != "exact" and incoming.match_type == "exact":
        current.match_type = "exact"


def _impact_from_path(artifact: Artifact, relation: Relation, target: Impact) -> Impact:
    path = f"{target.relation_paths[0]} <- {relation.relation_type} - {artifact.artifact_id}"
    inferred = relation.polarity == "inferred" and relation.status != "confirmed"
    return Impact(
        artifact_id=artifact.artifact_id,
        display_name=artifact.display_name,
        artifact_type=artifact.artifact_type,
        review_priority="may_review" if inferred else "should_review",
        evidence_strength="weak" if inferred else "medium",
        match_type=relation.match_type,
        relation_distance=2,
        rule_assessment="explicit_relation",
        reason="A two-hop explicit relation path to the changed entity was found.",
        relation_paths=[path],
        evidence_ids=sorted({*target.evidence_ids, *relation.evidence_ids}),
        relation_statuses=sorted({*target.relation_statuses, relation.status}),
        needs_review=True,
    )


def _priority_for(relation: Relation) -> str:
    if (relation.polarity == "inferred" and relation.status != "confirmed") or (
        relation.relation_type == "MENTIONS"
    ):
        return "may_review"
    if relation.relation_type in MUST_RELATIONS:
        return "must_review"
    if relation.relation_type in SHOULD_RELATIONS:
        return "should_review"
    return "may_review"


def _detect_changed_entities(store: LocalStore, title: str, body: str) -> list[str]:
    text = f"{title}\n{body}"
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    matches = []
    for entity in store.read("entities", Entity):
        if _is_llm_only(entity):
            continue
        names = {entity.display_name, *entity.aliases, *aliases.aliases_for(entity.entity_id)}
        if any(name and name in text for name in names):
            matches.append(entity.entity_id)
    return sorted(set(matches))


def _write_trace(
    store: LocalStore,
    run_dir: Path,
    changed_entities: list[str],
    impacts: list[Impact],
    rejected: dict[str, list[str]],
    suggestions: list[dict[str, str]] | None = None,
    llm_rows: list[dict[str, object]] | None = None,
) -> None:
    included = {item.artifact_id: item for item in impacts}
    rows = [
        {
            "event": "analyze",
            "changed_entities": changed_entities,
            "changed_entity_suggestions": [
                {
                    "name_hash": _trace_hash(item.get("name", "")),
                    "reason_hash": _trace_hash(item.get("reason", "")),
                }
                for item in suggestions or []
            ],
        },
        *(llm_rows or []),
    ]
    for artifact in sorted(store.read("artifacts", Artifact), key=lambda item: item.artifact_id):
        impact = included.get(artifact.artifact_id)
        rejected_ids = rejected.get(artifact.artifact_id, [])
        reason = (
            impact.reason
            if impact
            else f"Rejected relations: {', '.join(rejected_ids)}"
            if rejected_ids
            else "No relation to the changed entities was found."
        )
        rows.append(
            {
                "event": "candidate",
                "artifact_id": artifact.artifact_id,
                "included": impact is not None,
                "review_priority": impact.review_priority if impact else "hidden",
                "relation_statuses": impact.relation_statuses
                if impact
                else ["rejected"]
                if rejected_ids
                else [],
                "reason": reason,
            }
        )
    store.write_text(
        run_dir / "trace.jsonl",
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )


def render_markdown(report: Report, store: LocalStore) -> str:
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    lines = [
        f"# SpecImpact Report: {report.change.title}",
        "",
        "> This report lists review candidates, not confirmed impacts.",
        '> `must_review` means "must be checked", not "confirmed affected".',
        "",
        "> このレポートは影響確定結果ではなく、レビュー候補です。",
        "> `must_review` は「影響あり」ではなく「必ず確認すべき」です。",
        "",
        "## Change",
        "",
        report.change.body,
        "",
        "## Summary",
        "",
        "- must_review: "
        f"{sum(1 for item in report.impacts if item.review_priority == 'must_review')}",
        "- should_review: "
        f"{sum(1 for item in report.impacts if item.review_priority == 'should_review')}",
        "- may_review: "
        f"{sum(1 for item in report.impacts if item.review_priority == 'may_review')}",
        "",
    ]
    for priority, heading in (
        ("must_review", "Must Review"),
        ("should_review", "Should Review"),
        ("may_review", "May Review"),
    ):
        lines.extend([f"## {heading}", ""])
        for impact in (item for item in report.impacts if item.review_priority == priority):
            lines.extend(
                [
                    f"### {impact.display_name}",
                    f"- Artifact ID: {impact.artifact_id}",
                    f"- Type: {impact.artifact_type}",
                    f"- Reason: {impact.reason}",
                    f"- Evidence strength: {impact.evidence_strength}",
                    f"- Rule assessment: {impact.rule_assessment}",
                    f"- Relation statuses: {', '.join(impact.relation_statuses) or 'direct_match'}",
                    *(f"- Warning: {warning}" for warning in impact.warnings),
                    *(
                        [
                            f"- LLM judgement: {impact.llm_judgement}",
                            f"- LLM reason: {impact.llm_reason}",
                        ]
                        if impact.llm_judgement
                        else []
                    ),
                    "- Relation path:",
                    *(f"  - {path}" for path in impact.relation_paths),
                    "- Evidence:",
                ]
            )
            if impact.evidence_ids:
                for evidence_id in impact.evidence_ids:
                    if evidence_id not in evidence:
                        lines.append(f"  - Missing evidence: {evidence_id}")
                        continue
                    item = evidence[evidence_id]
                    lines.append(
                        f"  - {item.source_location.file}:"
                        f"{item.source_location.line_start}-{item.source_location.line_end}: "
                        f"{item.quote}"
                    )
            else:
                lines.append("  - Change request direct match")
            lines.append("")
    return "\n".join(lines)


def latest_run_dir(store: LocalStore) -> Path:
    path = store.root / "latest_run"
    if not path.exists():
        raise ValueError("No analysis run exists")
    return store.root / "runs" / path.read_text(encoding="utf-8").strip()


def alias_index(store: LocalStore) -> dict[str, set[str]]:
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    index: dict[str, set[str]] = {}
    for artifact in store.read("artifacts", Artifact):
        for name in {
            artifact.artifact_id,
            artifact.display_name,
            *artifact.aliases,
            *aliases.aliases_for(artifact.artifact_id),
        }:
            index.setdefault(name, set()).add(artifact.artifact_id)
    for entity in store.read("entities", Entity):
        for name in {
            entity.entity_id,
            entity.display_name,
            entity.canonical_name,
            *entity.aliases,
            *aliases.aliases_for(entity.entity_id),
        }:
            index.setdefault(name, set()).add(entity.entity_id)
    return index


def resolve_name(store: LocalStore, name: str) -> str | None:
    candidates = alias_index(store).get(name, set())
    if len(candidates) > 1:
        raise AmbiguousAliasError(name, list(candidates))
    return next(iter(candidates), None)


def explain_why(store: LocalStore, name: str) -> str:
    try:
        item_id = resolve_name(store, name)
    except AmbiguousAliasError as error:
        return str(error)
    if not item_id:
        return f'Could not resolve "{name}".'
    data = json.loads((latest_run_dir(store) / "report.json").read_text(encoding="utf-8"))
    impact = next(
        (
            item
            for group in ("must_review", "should_review", "may_review", "hidden")
            for item in data[group]
            if item["artifact_id"] == item_id
        ),
        None,
    )
    if not impact:
        trace = _trace_for(store, item_id)
        return (
            f'Resolved "{name}" to artifact_id: {item_id}\n\n'
            f"Candidate state: excluded\nReason: {trace['reason']}"
        )
    lines = [
        f'Resolved "{name}" to artifact_id: {item_id}',
        "",
        f"Review priority:\n{impact['review_priority']}",
        "",
        "Reasons:",
        f"- {impact['reason']}",
    ]
    if impact["relation_distance"] == 0:
        lines.append("- Direct change-request match; no relation evidence is required.")
    else:
        lines.append("- The relation is supported by local evidence.")
    lines.extend(
        [
            "",
            "Relation paths:",
            *(f"- {path}" for path in impact["relation_paths"]),
            "",
            "Evidence:",
        ]
    )
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    if not impact["evidence_ids"]:
        lines.append("- Change request direct match")
    for evidence_id in impact["evidence_ids"]:
        item = evidence[evidence_id]
        lines.extend(
            [f"- {evidence_id}", f"  file: {item.source_location.file}", f"  quote: {item.quote}"]
        )
    return "\n".join(lines)


def _trace_for(store: LocalStore, artifact_id: str) -> dict[str, object]:
    path = latest_run_dir(store) / "trace.jsonl"
    return next(
        (
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("artifact_id") == artifact_id
        ),
        {"reason": "No trace data was recorded."},
    )


def _semantic_impacts(
    store: LocalStore,
    body: str,
    embedding_client: EmbeddingClient | None,
    *,
    yes: bool,
    confirm: Callable[[str], bool] | None,
) -> list[Impact]:
    if not body:
        return []
    config = load_config(store)
    ranked = semantic_search(
        store,
        body,
        top_k=config["retrieval"]["semantic_top_k"],
        client=embedding_client,
        yes=yes,
        confirm=confirm,
    )
    if not ranked:
        return []
    chunk_ids = {chunk_id for chunk_id, _score in ranked}
    evidence = [item for item in store.read("evidence", Evidence) if item.chunk_id in chunk_ids]
    relations = {item.relation_id: item for item in store.read("relations", Relation)}
    artifacts = {item.artifact_id: item for item in store.read("artifacts", Artifact)}
    impacts: dict[str, Impact] = {}
    for item in evidence:
        for support in item.supports:
            if support.type != "relation" or support.id not in relations:
                continue
            relation = relations[support.id]
            artifact = artifacts.get(relation.source_id)
            if not artifact or relation.status == "rejected":
                continue
            candidate = Impact(
                artifact_id=artifact.artifact_id,
                display_name=artifact.display_name,
                artifact_type=artifact.artifact_type,
                review_priority="may_review",
                evidence_strength="weak",
                match_type="semantic",
                relation_distance=1,
                rule_assessment="inferred_relation",
                reason="A semantically related local chunk with evidence was retrieved.",
                relation_paths=[
                    f"change ~ semantic chunk {item.chunk_id} <- evidence - {artifact.artifact_id}"
                ],
                evidence_ids=[item.evidence_id],
                relation_statuses=[relation.status],
                needs_review=True,
            )
            if artifact.artifact_id in impacts:
                _merge_impact(impacts[artifact.artifact_id], candidate)
            else:
                impacts[artifact.artifact_id] = candidate
    return list(impacts.values())


def _rerank_impacts(
    store: LocalStore,
    body: str,
    impacts: list[Impact],
    client: LLMClient,
) -> list[dict[str, object]]:
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    chunks = {item.chunk_id: item for item in store.read("chunks", Chunk)}
    traces = []
    for batch in _batched_impacts(impacts, RERANK_BATCH_SIZE):
        payload = {
            "change_request": body,
            "candidates": [_rerank_candidate_payload(impact, evidence, chunks) for impact in batch],
        }
        results, trace = rerank_batch(client, payload)
        for impact in batch:
            result = results.get(impact.artifact_id)
            if not result:
                continue
            impact.llm_judgement = result.llm_judgement
            impact.llm_reason = result.llm_reason
            impact.selected_evidence_ids = result.selected_evidence_ids
            _apply_rerank_guardrails(impact)
        traces.append(trace)
    impacts.sort(key=lambda item: (PRIORITY_ORDER[item.review_priority], item.artifact_id))
    return traces


def _rerank_candidate_payload(
    impact: Impact,
    evidence: dict[str, Evidence],
    chunks: dict[str, Chunk],
) -> dict[str, object]:
    local_evidence = [evidence[item_id] for item_id in impact.evidence_ids if item_id in evidence]
    return {
        "artifact_id": impact.artifact_id,
        "display_name": impact.display_name,
        "artifact_type": impact.artifact_type,
        "rule_assessment": impact.rule_assessment,
        "review_priority": impact.review_priority,
        "relation_paths": impact.relation_paths,
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "quote": item.quote,
                "source_location": item.source_location.model_dump(),
                "chunk_excerpt": chunks[item.chunk_id].text if item.chunk_id in chunks else "",
            }
            for item in local_evidence
        ],
    }


def _batched_impacts(items: list[Impact], size: int) -> list[list[Impact]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _apply_rerank_guardrails(impact: Impact) -> None:
    protected_must = impact.review_priority == "must_review" and impact.rule_assessment in {
        "direct_match",
        "explicit_relation",
    }
    if protected_must:
        return
    if impact.llm_judgement == "impact" and impact.selected_evidence_ids:
        if impact.review_priority in {"may_review", "hidden"}:
            impact.review_priority = "should_review"
            impact.evidence_strength = "medium"
        return
    if impact.llm_judgement == "no_impact":
        impact.review_priority = "may_review"
        impact.evidence_strength = "weak"


def _is_llm_only(item: Entity) -> bool:
    return item.extraction_methods == ["llm"]


def _trace_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
