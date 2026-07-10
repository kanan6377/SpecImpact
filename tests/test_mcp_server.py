from __future__ import annotations

import asyncio
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specimpact.application import Project, project_from_path
from specimpact.application.approval import ApprovalManager
from specimpact.application.resources import ResourceReader
from specimpact.cli import app
from specimpact.mcp_server import (
    TransmissionApprovalChoice,
    _evidence_metadata,
    _source_metadata,
    create_mcp_server,
)
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

runner = CliRunner()


def _project(path: Path) -> Project:
    path.mkdir(parents=True, exist_ok=True)
    return project_from_path(path)


def test_approval_grant_is_bound_single_use_and_body_free(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    manager = ApprovalManager(project)
    payload = {
        "evidence": [
            {"evidence_id": "ev-1", "quote": "email: person@example.com API_KEY=secret12345"}
        ]
    }
    preview = manager.create_preview(
        purpose="impact-analysis",
        host="cursor",
        provider="host",
        model="test-model",
        payload=payload,
        evidence_ids=["ev-1"],
    )

    preview_text = (manager.store_root / "transmission_previews.jsonl").read_text(
        encoding="utf-8"
    )
    assert preview.redacted is True
    assert "person@example.com" not in preview_text
    assert "secret12345" not in preview_text

    grant = manager.issue_grant(preview.preview_id, decision="approve")
    grant_text = manager.grant_path.read_text(encoding="utf-8")
    assert grant.token not in grant_text
    assert manager.consume(
        grant.token,
        purpose=preview.purpose,
        source_hash=preview.source_hash,
    ) == grant.grant_id
    with pytest.raises(ValueError, match="already used"):
        manager.consume(
            grant.token,
            purpose=preview.purpose,
            source_hash=preview.source_hash,
        )


def test_approval_grant_rejects_expiry_scope_and_other_project(tmp_path: Path) -> None:
    project = _project(tmp_path / "a")
    manager = ApprovalManager(project)
    preview = manager.create_preview(
        purpose="region-extraction",
        host="antigravity",
        payload={"items": ["one"]},
    )
    grant = manager.issue_grant(preview.preview_id, decision="approve")
    with pytest.raises(ValueError, match="does not match"):
        manager.consume(grant.token, purpose="impact-analysis", source_hash=preview.source_hash)

    other = ApprovalManager(_project(tmp_path / "b"))
    other.store_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manager.grant_path, other.grant_path)
    with pytest.raises(ValueError, match="another project"):
        other.consume(
            grant.token,
            purpose=preview.purpose,
            source_hash=preview.source_hash,
        )

    expired = manager.create_preview(
        purpose="expired",
        host="cursor",
        payload={"items": []},
    )
    expired.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    manager.store.write("transmission_previews", [preview, expired])
    with pytest.raises(ValueError, match="expired"):
        manager.issue_grant(expired.preview_id, decision="approve")


def test_resources_paginate_and_reject_unknown_ids(tmp_path: Path) -> None:
    project = _project(tmp_path / "project")
    store = LocalStore(Path(project.path) / ".specimpact")
    store.init()
    source = Path(project.path) / "docs" / "design.md"
    source.parent.mkdir()
    source.write_text("# Design\nfield one\nfield two\n", encoding="utf-8")
    document = Document(
        document_id="doc-1",
        path="docs/design.md",
        title="Design",
        hash="hash",
    )
    chunk = Chunk(
        chunk_id="chunk-1",
        document_id=document.document_id,
        section_id="section-1",
        text="field one\nfield two",
        line_start=2,
        line_end=3,
    )
    evidence = Evidence(
        evidence_id="ev-1",
        document_id=document.document_id,
        section_id="section-1",
        chunk_id=chunk.chunk_id,
        quote="field one",
        evidence_type="explicit",
        supports=[EvidenceSupport(type="entity", id="entity-1")],
        source_location=SourceLocation(file="docs/design.md", line_start=2, line_end=2),
    )
    store.write("documents", [document])
    store.write("chunks", [chunk])
    store.write("evidence", [evidence])
    store.write(
        "artifacts",
        [
            Artifact(
                artifact_id="artifact-1",
                artifact_type="screen",
                display_name="Screen",
                source_document_ids=[document.document_id],
            )
        ],
    )
    store.write(
        "entities",
        [
            Entity(
                entity_id="entity-1",
                entity_type="field",
                display_name="Field",
                canonical_name="field",
                source_document_ids=[document.document_id],
            )
        ],
    )
    store.write(
        "relations",
        [
            Relation(
                relation_id="rel-1",
                relation_type="contains",
                source_id="artifact-1",
                target_id="entity-1",
                evidence_ids=[evidence.evidence_id],
                source_document_ids=[document.document_id],
            )
        ],
    )
    resources = ResourceReader(project)

    first = resources.source_resource(document.document_id, limit=1)
    assert len(first["items"]) == 1
    assert first["next_cursor"] == "1"
    second = resources.source_resource(
        document.document_id,
        cursor=first["next_cursor"],
        limit=1,
    )
    assert second["cursor"] == "1"
    assert resources.evidence_resource("ev-1")["quote"] == "field one"
    assert resources.graph_resource("entity-1")["total"] == 1
    with pytest.raises(KeyError, match="Unknown evidence"):
        resources.evidence_resource("missing")
    with pytest.raises(ValueError, match="limit"):
        resources.source_resource(document.document_id, limit=501)


def test_mcp_exposes_typed_tools_resources_and_prompts(tmp_path: Path) -> None:
    async def inspect_server() -> None:
        server = create_mcp_server(tmp_path)
        tools = {item.name: item for item in await server.list_tools()}
        assert "execute" not in tools
        assert {
            "prepare_graph_context",
            "submit_graph_extraction",
            "authorize_prepared_context",
            "prepare_change",
            "submit_change_atoms",
            "prepare_impact_context",
            "submit_impact_hypotheses",
            "ingest_sources",
            "get_change_session",
            "set_impact_decision",
            "resolve_alias",
            "decide_graph_proposal",
            "open_evidence",
            "export_obsidian",
            "get_job",
            "list_jobs",
            "cancel_job",
        } <= set(tools)
        assert "idempotency_key" in tools["ingest_sources"].inputSchema["required"]
        assert "idempotency_key" in tools["submit_change_atoms"].inputSchema["required"]
        assert "idempotency_key" in tools["submit_impact_hypotheses"].inputSchema["required"]
        prompts = {item.name for item in await server.list_prompts()}
        assert prompts == {
            "specimpact-onboard",
            "specimpact-ingest",
            "specimpact-change",
            "specimpact-review",
        }
        templates = {str(item.uriTemplate) for item in await server.list_resource_templates()}
        assert "specimpact://projects/{project_id}" in templates
        assert "specimpact://graph/{node_id}/pages/{cursor}" in templates

        runtime = server._specimpact_runtime
        contents = await server.read_resource(
            f"specimpact://projects/{runtime.project.project_id}"
        )
        project_payload = json.loads(list(contents)[0].content)
        assert project_payload["onboarding_required"] is True
        runtime.service.store.init()
        jobs = await server.call_tool("list_jobs", {"limit": 5})
        assert json.loads(jobs[0].text) == {"jobs": [], "limit": 5}

    asyncio.run(inspect_server())


def test_transmission_approval_choice_round_trip() -> None:
    choice = TransmissionApprovalChoice(decision="approve")
    assert TransmissionApprovalChoice.model_validate(choice.model_dump()) == choice


def test_mcp_resource_metadata_does_not_expose_source_bodies() -> None:
    source = _source_metadata(
        {
            "source": {"document_id": "doc-1"},
            "items": [
                {"kind": "row", "line": 3, "text": "secret design body"},
                {"kind": "cell", "cell": "A1", "value": "secret cell"},
            ],
            "next_cursor": None,
        }
    )
    evidence = _evidence_metadata({"evidence_id": "ev-1", "quote": "secret quote"})
    assert "secret" not in json.dumps(source)
    assert "secret" not in json.dumps(evidence)
    assert source["content_withheld"] is True
    assert evidence["content_withheld"] is True


def test_rest_contract_schema_is_generated_from_shared_models(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from specimpact.webui.app import create_app

    with TestClient(
        create_app(registry_root=tmp_path / "registry"),
        base_url="http://127.0.0.1",
    ) as client:
        response = client.get("/api/contracts/v1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["version"] == "v1"
    assert "PreparedContext" in payload["schemas"]


def test_mcp_cli_rejects_non_stdio_transport(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["mcp", "--project", str(tmp_path), "--no-stdio"],
    )
    assert result.exit_code != 0
    assert "Only the stdio transport is supported" in result.output
