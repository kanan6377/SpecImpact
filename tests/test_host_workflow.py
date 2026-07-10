from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from specimpact.application import HostContext, project_from_path
from specimpact.application.approval import ApprovalManager
from specimpact.application.host_workflow import (
    HostImpactHypothesis,
    HostImpactSubmission,
    HostWorkflow,
)
from specimpact.dirty_excel.models import DirtyCell, DirtyRegion
from specimpact.models import (
    Artifact,
    Chunk,
    Document,
    Entity,
    Evidence,
    EvidenceSupport,
    Relation,
    SourceLocation,
)
from specimpact.store import LocalStore

CHANGE_ID = "change.credit-limit"
ARTIFACT_ID = "artifact.credit-limit-api"
EVIDENCE_ID = "evidence.credit-limit-current"
BODY_MARKER = "HOST_WORKFLOW_BODY_DO_NOT_PERSIST"
AUDIT_LEDGER_NAMES = (
    "transmission_previews.jsonl",
    "approval_grants.jsonl",
    "trace.jsonl",
    "host_warnings.jsonl",
    "idempotency.jsonl",
)


@pytest.fixture
def workflow(tmp_path: Path) -> HostWorkflow:
    project_path = tmp_path / "project"
    project_path.mkdir()
    project = project_from_path(project_path)
    _write_minimal_graph(project_path)
    return HostWorkflow(
        project,
        HostContext(
            host="fake-external-host",
            workspace_root=str(project_path),
            project_id=project.project_id,
            model="fake-host-model",
            capabilities=["sampling"],
            external=True,
        ),
    )


def test_external_host_withholds_change_payload_until_authorized_and_audit_is_body_free(
    workflow: HostWorkflow,
) -> None:
    prepared = workflow.prepare_change(_change_text())

    assert prepared.transmission_preview is not None
    assert prepared.transmission_preview.external is True
    assert prepared.transmission_preview.required is True
    assert BODY_MARKER not in _json(prepared.payload)

    grant = ApprovalManager(workflow.project).issue_grant(
        prepared.transmission_preview.preview_id,
        decision="approve",
    )
    authorized = workflow.authorize_context(prepared.context_id, grant.token)

    assert authorized.context_id == prepared.context_id
    assert BODY_MARKER in _json(authorized.payload)
    assert BODY_MARKER not in _audit_ledger_state(Path(workflow.project.path) / ".specimpact")


def test_change_atom_submission_rejects_schema_and_before_value_mismatches(
    workflow: HostWorkflow,
) -> None:
    context_id, change_id = _authorized_change_context(workflow)

    with pytest.raises(ValueError, match="schema"):
        workflow.submit_change_atoms(
            context_id,
            {
                "change_id": change_id,
                "change_atoms": [
                    {
                        "atom_id": "atom.invalid",
                        "change_id": change_id,
                        "operation": "change_constraint",
                    }
                ],
            },
            "invalid-change-atom",
        )

    with pytest.raises(ValueError, match="before"):
        workflow.submit_change_atoms(
            context_id,
            _change_atom_payload(change_id, before="999"),
            "mismatched-before-value",
        )


def test_impact_submission_rejects_unknown_evidence_and_nodes(workflow: HostWorkflow) -> None:
    change_id = _submit_valid_change_atom(workflow).change_id
    context_id = _authorized_impact_context(workflow, change_id)

    with pytest.raises(ValueError, match="(?i)(node|candidate)"):
        workflow.submit_impact_hypotheses(
            context_id,
            _impact_payload(
                change_id,
                candidate_node_id="artifact.missing",
                evidence_ids=[EVIDENCE_ID],
            ),
            "unknown-node",
        )

    with pytest.raises(ValueError, match="(?i)evidence"):
        workflow.submit_impact_hypotheses(
            context_id,
            _impact_payload(
                change_id,
                candidate_node_id=ARTIFACT_ID,
                evidence_ids=["evidence.missing"],
            ),
            "unknown-evidence",
        )


def test_llm_only_must_review_is_downgraded_and_impact_submission_is_idempotent(
    workflow: HostWorkflow,
) -> None:
    change_id = _submit_valid_change_atom(workflow).change_id
    context_id = _authorized_impact_context(workflow, change_id)
    payload = _impact_payload(change_id, candidate_node_id=ARTIFACT_ID, evidence_ids=[])

    first = workflow.submit_impact_hypotheses(context_id, payload, "llm-only-impact")
    replay = workflow.submit_impact_hypotheses(context_id, payload, "llm-only-impact")

    assert replay == first
    assert len(replay.impacts) == 1
    assert replay.impacts[0]["review_priority"] in {"may_review", "hidden"}
    assert BODY_MARKER not in _audit_ledger_state(Path(workflow.project.path) / ".specimpact")


def test_host_impact_payloads_are_typed_models() -> None:
    hypothesis = HostImpactHypothesis(
        candidate_node_id=ARTIFACT_ID,
        atom_id="atom.credit-limit",
        impact_type="constraint_change",
        required_actions=["Update the API contract."],
        warnings=[],
        uncertainty="medium",
        reason="Evidence-backed host response.",
        evidence_ids=[EVIDENCE_ID],
        relation_ids=["relation.credit-limit"],
        review_priority_suggestion="must_review",
    )
    submission = HostImpactSubmission(change_id="change.host.example", hypotheses=[hypothesis])

    assert isinstance(submission, BaseModel)
    assert HostImpactSubmission.model_validate(submission.model_dump()) == submission


def test_dirty_region_host_extraction_is_approval_gated_and_evidence_verified(
    workflow: HostWorkflow,
) -> None:
    prepared = workflow.prepare_graph_context("region.credit-limit")
    assert prepared.payload["withheld"] is True
    grant = ApprovalManager(workflow.project).issue_grant(
        prepared.transmission_preview.preview_id,
        decision="approve",
    )
    authorized = workflow.authorize_context(prepared.context_id, grant.token)
    assert authorized.payload["region_id"] == "region.credit-limit"

    submission = {
        "region_id": "region.credit-limit",
        "nodes": [
            {
                "temp_id": "n1",
                "node_type": "APIField",
                "display_name": "creditLimit",
                "evidence_ids": [EVIDENCE_ID],
                "rationale": "Explicit row",
            }
        ],
        "edges": [],
    }
    proposal = workflow.submit_graph_extraction(
        prepared.context_id,
        submission,
        "host-region-extraction",
    )
    assert proposal.status == "pending"
    assert proposal.extraction_method == "llm"

    submission["nodes"][0]["evidence_ids"] = ["evidence.missing"]
    with pytest.raises(ValueError, match="Evidence"):
        workflow.submit_graph_extraction(
            prepared.context_id,
            submission,
            "host-region-invalid-evidence",
        )


def _authorized_change_context(workflow: HostWorkflow) -> tuple[str, str]:
    prepared = workflow.prepare_change(_change_text())
    assert prepared.transmission_preview is not None
    grant = ApprovalManager(workflow.project).issue_grant(
        prepared.transmission_preview.preview_id,
        decision="approve",
    )
    context_id = workflow.authorize_context(prepared.context_id, grant.token).context_id
    return context_id, workflow._context_record(context_id)["change_id"]


def _authorized_impact_context(workflow: HostWorkflow, change_id: str) -> str:
    prepared = workflow.prepare_impact_context(change_id)
    assert prepared.transmission_preview is not None
    grant = ApprovalManager(workflow.project).issue_grant(
        prepared.transmission_preview.preview_id,
        decision="approve",
    )
    return workflow.authorize_context(prepared.context_id, grant.token).context_id


def _submit_valid_change_atom(workflow: HostWorkflow):
    context_id, change_id = _authorized_change_context(workflow)
    return workflow.submit_change_atoms(
        context_id,
        _change_atom_payload(change_id, before="100"),
        "valid-change-atom",
    )


def _change_text() -> str:
    return (
        f"# Increase credit limit\n\n{BODY_MARKER}\n"
        "Change creditLimit maximum from 100 to 200."
    )


def _change_atom_payload(change_id: str, *, before: str) -> dict[str, object]:
    return {
        "change_id": change_id,
        "change_atoms": [
            {
                "atom_id": "atom.credit-limit",
                "change_id": change_id,
                "target_terms": ["creditLimit"],
                "operation": "change_constraint",
                "property": "max_value",
                "before": before,
                "after": "200",
                "likely_node_types": ["APIField"],
            }
        ],
    }


def _impact_payload(
    change_id: str,
    *,
    candidate_node_id: str,
    evidence_ids: list[str],
) -> dict[str, object]:
    return HostImpactSubmission(
        change_id=change_id,
        hypotheses=[
            HostImpactHypothesis(
                candidate_node_id=candidate_node_id,
                atom_id="atom.credit-limit",
                impact_type="constraint_change",
                required_actions=["Update the API contract."],
                warnings=[],
                uncertainty="medium",
                reason="Host model predicts an impact.",
                evidence_ids=evidence_ids,
                relation_ids=[],
                review_priority_suggestion="must_review",
            )
        ],
    ).model_dump()


def _write_minimal_graph(project_path: Path) -> None:
    store = LocalStore(project_path / ".specimpact")
    store.init()
    document = Document(
        document_id="document.api",
        path="docs/api.md",
        title="Credit limit API",
        hash="document-hash",
    )
    chunk = Chunk(
        chunk_id="chunk.credit-limit",
        document_id=document.document_id,
        section_id="section.credit-limit",
        text="creditLimit maximum is 100.",
        line_start=1,
        line_end=1,
    )
    evidence = Evidence(
        evidence_id=EVIDENCE_ID,
        document_id=document.document_id,
        section_id=chunk.section_id,
        chunk_id=chunk.chunk_id,
        quote="creditLimit maximum is 100.",
        evidence_type="explicit",
        supports=[EvidenceSupport(type="entity", id="entity.credit-limit")],
        source_location=SourceLocation(file=document.path, line_start=1, line_end=1),
    )
    artifact = Artifact(
        artifact_id=ARTIFACT_ID,
        artifact_type="APIField",
        display_name="creditLimit",
        source_document_ids=[document.document_id],
    )
    entity = Entity(
        entity_id="entity.credit-limit",
        entity_type="field",
        display_name="creditLimit",
        canonical_name="credit_limit",
        source_document_ids=[document.document_id],
    )
    relation = Relation(
        relation_id="relation.credit-limit",
        relation_type="maps_to",
        source_id=ARTIFACT_ID,
        target_id=entity.entity_id,
        evidence_ids=[evidence.evidence_id],
        source_document_ids=[document.document_id],
    )
    store.write("documents", [document])
    store.write("chunks", [chunk])
    store.write("artifacts", [artifact])
    store.write("entities", [entity])
    store.write("relations", [relation])
    store.write("evidence", [evidence])
    store.write(
        "dirty_regions",
        [
            DirtyRegion(
                region_id="region.credit-limit",
                workbook_id="workbook.credit-limit",
                sheet_id="sheet.api",
                sheet_name="API items",
                range="A1:B2",
                region_type="api_mapping_table",
                rendered_text="| item | value |\n| creditLimit | 100 |",
                evidence_ids=[EVIDENCE_ID],
                start_row=1,
                end_row=2,
                start_column=1,
                end_column=2,
            )
        ],
    )
    store.write(
        "dirty_cells",
        [
            DirtyCell(
                workbook_id="workbook.credit-limit",
                file_path="docs/api.xlsx",
                sheet_id="sheet.api",
                sheet_name="API items",
                cell="A2",
                evidence_id=EVIDENCE_ID,
                value="creditLimit",
                data_type="s",
                row=2,
                column=1,
            )
        ],
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _audit_ledger_state(store_root: Path) -> str:
    return "\n".join(
        (store_root / name).read_text(encoding="utf-8", errors="ignore")
        for name in AUDIT_LEDGER_NAMES
        if (store_root / name).is_file()
    )
