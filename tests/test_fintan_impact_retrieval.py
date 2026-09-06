from __future__ import annotations

from pathlib import Path

from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.impact_management.impact_hypothesis import build_impact_hypotheses
from specimpact.impact_management.impact_retrieval import retrieve_impacts
from specimpact.models import Artifact, Entity, Evidence, EvidenceSupport, Relation, SourceLocation
from specimpact.store import LocalStore


def test_equal_distance_regions_keep_boundary_evidence_for_table(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    store.write(
        "entities",
        [
            Entity(
                entity_id="entity.project_name",
                entity_type="BusinessField",
                display_name="プロジェクト名",
                canonical_name="project_name",
            )
        ],
    )
    store.write(
        "artifacts",
        [
            Artifact(
                artifact_id="table.project",
                artifact_type="Table",
                display_name="プロジェクトテーブル定義",
            )
        ],
    )
    relations = []
    evidence = []
    for suffix, quote in (
        ("name", "[B12] プロジェクト名 [G12] PROJECT_NAME"),
        ("length", "[B12] プロジェクト名 [T12] 128"),
    ):
        relation_id = f"rel.project.{suffix}"
        evidence_id = f"ev.project.{suffix}"
        relations.append(
            Relation(
                relation_id=relation_id,
                relation_type="DEFINES",
                source_id="table.project",
                target_id="entity.project_name",
                evidence_ids=[evidence_id],
            )
        )
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                document_id="doc.project",
                section_id="sec.project",
                chunk_id=f"chunk.{suffix}",
                quote=quote,
                evidence_type="dirty_excel_cell_mention",
                supports=[EvidenceSupport(type="relation", id=relation_id)],
                source_location=SourceLocation(file="table.xlsx", line_start=12, line_end=12),
            )
        )
    store.write("relations", relations)
    store.write("evidence", evidence)
    atom = ChangeAtom(
        atom_id="atom.project-name",
        change_id="change.project-name",
        target_terms=["プロジェクト名"],
        operation="change_constraint",
        property="length",
        before="128",
        after="256",
    )

    retrieved = retrieve_impacts(store, [atom])

    path = next(item for item in retrieved if item.node_id == "table.project")
    assert path.evidence_ids == ["ev.project.length", "ev.project.name"]
    impacts = build_impact_hypotheses(store, [atom], retrieved)
    impact = next(item for item in impacts if item.artifact_id == "table.project")
    assert impact.review_priority == "must_review"
