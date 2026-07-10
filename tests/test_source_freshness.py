from __future__ import annotations

from pathlib import Path

from specimpact.impact_management.decision_store import set_impact_status
from specimpact.inspection import set_relation_status
from specimpact.models import (
    Artifact,
    Chunk,
    Document,
    Entity,
    Evidence,
    EvidenceSupport,
    Relation,
    Section,
    SourceLocation,
)
from specimpact.source_freshness import (
    GraphDiffRecord,
    SourceVersion,
    StaleRecord,
    decide_graph_diff,
    freshness_data,
    resolve_stale,
)
from specimpact.store import LocalStore
from specimpact.webui.registry import ProjectRegistry
from specimpact.webui.services import graph_data, review_queue_data, source_library_data


def test_source_change_records_versions_diff_and_stale_dependencies(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    first = _graph("hash-one", "entity.limit", "100万円")
    store.merge_graph(**first)
    set_relation_status(store, "rel.screen.limit", "confirmed")
    set_impact_status(store, "impact.change.test.screen.main", "accepted", "reviewed")
    store.write_json(
        store.root / "runs" / "run-one" / "report.json",
        {
            "change": {"change_id": "change.test"},
            "must_review": [
                {
                    "artifact_id": "screen.main",
                    "evidence_ids": ["ev.limit"],
                }
            ],
            "should_review": [],
            "may_review": [],
            "hidden": [],
        },
    )
    store.write_text(store.root / "latest_run", "run-one")

    second = _graph("hash-two", "entity.limit.v2", "9999万円")
    store.merge_graph(**second)

    versions = store.read("source_versions", SourceVersion)
    assert [item.version_number for item in versions] == [1, 2]
    assert [item.change_type for item in versions] == ["added", "modified"]
    diffs = store.read("graph_diffs", GraphDiffRecord)
    assert diffs[0].status == "reviewed"
    assert diffs[-1].status == "pending"
    assert diffs[-1].changed_relation_ids == ["rel.screen.limit"]
    relation = store.read("relations", Relation)[0]
    assert relation.status == "unconfirmed"

    stale = [item for item in store.read("stale_records", StaleRecord) if item.resolved_at is None]
    assert {item.target_type for item in stale} == {"evidence", "relation", "impact", "node"}
    assert any(item.target_id == "impact.change.test.screen.main" for item in stale)
    assert any(item.target_id == "rel.screen.limit" for item in stale)

    project = ProjectRegistry(tmp_path / "registry").add(tmp_path)
    graph = graph_data(project)
    assert graph["edges"][0]["data"]["stale"] is True
    queue = review_queue_data(project)
    relation_item = next(item for item in queue["items"] if item["kind"] == "relation")
    impact_item = next(item for item in queue["items"] if item["kind"] == "impact")
    assert relation_item["status"] == "stale"
    assert impact_item["status"] == "stale"
    assert any(
        item["kind"] == "graph_diff" and item["status"] == "pending"
        for item in queue["items"]
    )
    source = source_library_data(project)["sources"][0]
    assert source["version_count"] == 2
    assert source["stale_count"] == len(stale)

    assert resolve_stale(store, "relation", "rel.screen.limit") == 1
    assert resolve_stale(store, "impact", "impact.change.test.screen.main") == 1
    decided = decide_graph_diff(store, diffs[-1].diff_id, "reviewed", "checked")
    assert decided.status == "reviewed"
    assert freshness_data(store)["summary"]["unresolved_stale"] == len(stale) - 2


def test_freshness_models_round_trip() -> None:
    version = SourceVersion(
        version_id="version.one",
        document_id="doc.one",
        source_path="one.md",
        version_number=1,
        content_hash="hash",
        change_type="added",
        graph_diff_id="diff.one",
    )
    diff = GraphDiffRecord(
        diff_id="diff.one",
        transaction_id="merge.one",
        document_ids=["doc.one"],
        added_relation_ids=["rel.one"],
    )
    stale = StaleRecord(
        stale_id="stale.one",
        target_type="relation",
        target_id="rel.one",
        document_id="doc.one",
        previous_hash="old",
        current_hash="new",
        reason="source modified",
    )
    assert SourceVersion.model_validate_json(version.model_dump_json()) == version
    assert GraphDiffRecord.model_validate_json(diff.model_dump_json()) == diff
    assert StaleRecord.model_validate_json(stale.model_dump_json()) == stale


def _graph(content_hash: str, target_id: str, quote: str) -> dict:
    document = Document(
        document_id="doc.source",
        path="source.md",
        title="Source",
        hash=content_hash,
    )
    section = Section(
        section_id="section.source",
        document_id=document.document_id,
        heading="Fields",
        level=2,
        line_start=1,
        line_end=2,
    )
    chunk = Chunk(
        chunk_id="chunk.source",
        document_id=document.document_id,
        section_id=section.section_id,
        text=quote,
        line_start=1,
        line_end=2,
    )
    artifact = Artifact(
        artifact_id="screen.main",
        artifact_type="Screen",
        display_name="Main screen",
        source_document_ids=[document.document_id],
    )
    entity = Entity(
        entity_id=target_id,
        entity_type="BusinessField",
        display_name="Limit",
        canonical_name="limit",
        source_document_ids=[document.document_id],
    )
    relation = Relation(
        relation_id="rel.screen.limit",
        relation_type="DISPLAYS",
        source_id=artifact.artifact_id,
        target_id=entity.entity_id,
        evidence_ids=["ev.limit"],
        source_document_ids=[document.document_id],
    )
    evidence = Evidence(
        evidence_id="ev.limit",
        document_id=document.document_id,
        section_id=section.section_id,
        chunk_id=chunk.chunk_id,
        quote=quote,
        evidence_type="explicit_relation",
        supports=[EvidenceSupport(type="relation", id=relation.relation_id)],
        source_location=SourceLocation(file=document.path, line_start=2, line_end=2),
    )
    return {
        "documents": [document],
        "sections": [section],
        "chunks": [chunk],
        "artifacts": [artifact],
        "entities": [entity],
        "relations": [relation],
        "evidence": [evidence],
    }
