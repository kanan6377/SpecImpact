from pathlib import Path

from fastapi.testclient import TestClient

from specimpact.application.approval import ApprovalManager
from specimpact.webui.app import create_app


def test_localhost_approval_page_issues_one_unpersisted_token(tmp_path: Path) -> None:
    app = create_app(registry_root=tmp_path / "registry")
    project = app.state.registry.create(tmp_path / "project")
    manager = ApprovalManager(project)
    preview = manager.create_preview(
        purpose="impact-hypothesis",
        host="antigravity",
        payload={"evidence": [{"evidence_id": "ev-1", "quote": "private quote"}]},
        evidence_ids=["ev-1"],
    )

    with TestClient(app, base_url="http://127.0.0.1") as client:
        page = client.get(
            f"/approval/{preview.preview_id}?project_id={project.project_id}"
        )
        assert page.status_code == 200
        assert "private quote" not in page.text
        endpoint = (
            f"/api/projects/{project.project_id}/transmission-previews/"
            f"{preview.preview_id}/approve"
        )
        assert client.post(endpoint).status_code == 403
        token = client.get("/api/session").json()["csrf_token"]
        response = client.post(
            endpoint,
            headers={
                "Origin": "http://127.0.0.1",
                "X-CSRF-Token": token,
            },
        )
        assert response.status_code == 200
        grant = response.json()["grant"]
        assert grant["token"] not in manager.grant_path.read_text(encoding="utf-8")
        assert client.post(
            endpoint,
            headers={
                "Origin": "http://127.0.0.1",
                "X-CSRF-Token": token,
            },
        ).status_code == 400

    assert manager.consume(
        grant["token"],
        purpose=preview.purpose,
        source_hash=preview.source_hash,
    ) == grant["grant_id"]
