from __future__ import annotations

from pathlib import Path

from specimpact.application import (
    ApplicationService,
    ApprovalGrant,
    ChangeSessionView,
    HostContext,
    JobHandle,
    PreparedContext,
    Project,
    TransmissionPreview,
    public_contract_schemas,
)
from specimpact.application.service import project_overview


def _preview() -> TransmissionPreview:
    return TransmissionPreview(
        preview_id="preview-1",
        project_id="project-1",
        purpose="impact-analysis",
        host="cursor",
        provider="host",
        model="test-model",
        external=True,
        required=True,
        item_count=2,
        redacted=True,
        source_hash="sha256:source",
        evidence_ids=["ev-1"],
        expires_at="2026-01-01T00:10:00+00:00",
    )


def test_public_contracts_round_trip() -> None:
    preview = _preview()
    values = [
        HostContext(
            host="cursor",
            workspace_root="/workspace",
            project_id="project-1",
            capabilities=["sampling"],
        ),
        preview,
        ApprovalGrant(
            grant_id="grant-1",
            token="secret-token",
            preview_id=preview.preview_id,
            project_id=preview.project_id,
            purpose=preview.purpose,
            source_hash=preview.source_hash,
            expires_at=preview.expires_at,
        ),
        PreparedContext(
            context_id="context-1",
            project_id="project-1",
            purpose="impact-analysis",
            schema_name="ImpactHypothesis",
            instructions="Return structured impact hypotheses.",
            payload={"change": "limit"},
            evidence_ids=["ev-1"],
            source_hash=preview.source_hash,
            transmission_preview=preview,
        ),
        JobHandle(
            job_id="job-1",
            project_id="project-1",
            action="ingest_sources",
            status="queued",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
        ChangeSessionView(
            session_id="session-1",
            project_id="project-1",
            change_id="change-1",
            title="Credit limit change",
            status="reviewing",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        ),
    ]

    for value in values:
        restored = type(value).model_validate(value.model_dump(mode="json"))
        assert restored == value


def test_public_contract_json_schemas_are_stable() -> None:
    schemas = public_contract_schemas()
    assert set(schemas) == {
        "ApprovalGrant",
        "ChangeSessionView",
        "HostContext",
        "JobHandle",
        "PreparedContext",
        "TransmissionPreview",
    }
    assert schemas["PreparedContext"]["properties"]["payload"]["type"] == "object"


def test_application_service_matches_legacy_web_query(tmp_path: Path) -> None:
    project = Project(
        project_id="project-1",
        display_name="Project",
        path=str(tmp_path),
        last_used_at="2026-01-01T00:00:00+00:00",
    )
    service = ApplicationService(project)
    service.store.init()

    assert service.overview() == project_overview(project)
    assert service.sources() == {"sources": []}
