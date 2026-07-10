from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from specimpact.models import Artifact, Entity, Evidence, Relation
from specimpact.operations import evaluate_dataset
from specimpact.store import LocalStore
from specimpact.webui.app import PAGES, create_app
from specimpact.webui.jobs import Job, JobManager
from specimpact.webui.registry import ProjectRegistry
from specimpact.webui.services import (
    copy_demo,
    demo_source,
    design_documents_data,
    execute,
    external_preview,
    graph_data,
    report_data,
    source_library_data,
)
from specimpact.webui.uploads import MAX_FILE_SIZE, MAX_FILES, sanitize_filename, save_uploads


def test_project_registry_add_deduplicates_creates_and_removes(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "registry")
    path = tmp_path / "new-project"
    project = registry.create(path, display_name="A")
    duplicate = registry.add(path, display_name="Renamed")
    assert duplicate.project_id == project.project_id
    assert duplicate.display_name == "Renamed"
    assert len(registry.list()) == 1
    registry.remove(project.project_id)
    assert registry.list() == []
    assert path.is_dir()


def test_project_registry_touch_is_thread_safe(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "registry")
    project = registry.create(tmp_path / "project")
    threads = [
        threading.Thread(target=registry.get, args=(project.project_id,), kwargs={"touch": True})
        for _ in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert registry.get(project.project_id).path == project.path


def test_uploads_are_managed_and_validated(tmp_path: Path) -> None:
    paths = save_uploads(tmp_path, "docs", [("one.md", b"# One"), ("two.txt", b"Two")])
    assert all(path.parent.parent.name == "uploads" for path in paths)
    assert paths[0].read_bytes() == b"# One"
    with pytest.raises(ValueError, match="basename"):
        sanitize_filename("../outside.md")
    with pytest.raises(ValueError, match="must use"):
        save_uploads(tmp_path, "change", [("bad.txt", b"text")])
    with pytest.raises(ValueError, match="exceeds"):
        save_uploads(tmp_path, "docs", [("huge.md", b"x" * (MAX_FILE_SIZE + 1))])
    with pytest.raises(ValueError, match="exceeds"):
        save_uploads(tmp_path, "docs", [(f"{item}.md", b"x") for item in range(MAX_FILES + 1)])


def test_jobs_are_serial_per_project_and_parallel_across_projects(tmp_path: Path) -> None:
    manager = JobManager()
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    other_started = threading.Event()

    def first():
        first_started.set()
        release_first.wait(timeout=2)
        return {"first": True}

    def second():
        second_started.set()
        return {"second": True}

    def other():
        other_started.set()
        return {"other": True}

    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    one = manager.enqueue("a", project_a, "first", first)
    assert first_started.wait(timeout=2)
    two = manager.enqueue("a", project_a, "second", second)
    three = manager.enqueue("b", project_b, "other", other)
    assert other_started.wait(timeout=2)
    assert not second_started.is_set()
    release_first.set()
    assert manager.wait("a", project_a, one.job_id).state == "succeeded"
    assert manager.wait("a", project_a, two.job_id).state == "succeeded"
    assert manager.wait("b", project_b, three.job_id).state == "succeeded"


def test_queued_job_can_be_cancelled_and_running_job_is_interrupted_on_reload(
    tmp_path: Path,
) -> None:
    manager = JobManager()
    started = threading.Event()
    release = threading.Event()

    def hold():
        started.set()
        release.wait(timeout=2)

    project = tmp_path / "project"
    first = manager.enqueue("project", project, "hold", hold)
    assert started.wait(timeout=2)
    second = manager.enqueue("project", project, "queued", lambda: None)
    assert manager.cancel("project", project, second.job_id).state == "cancelled"
    release.set()
    assert manager.wait("project", project, first.job_id).state == "succeeded"

    path = project / ".specimpact" / "gui" / "jobs.jsonl"
    queued = Job(project_id="project", action="queued", state="queued")
    running = Job(project_id="project", action="running", state="running")
    path.write_text(
        json.dumps(queued.model_dump()) + "\n" + json.dumps(running.model_dump()) + "\n",
        encoding="utf-8",
    )
    restarted = JobManager()
    jobs = restarted.list("project", project)
    assert {item.state for item in jobs} == {"interrupted"}


def test_job_error_summary_does_not_persist_exception_text(tmp_path: Path) -> None:
    manager = JobManager()
    project = tmp_path / "project"

    def fail() -> None:
        raise ValueError("secret-token document-body raw-provider-response")

    job = manager.enqueue("project", project, "fail", fail)
    assert manager.wait("project", project, job.job_id).state == "failed"
    history = project / ".specimpact" / "gui" / "jobs.jsonl"
    text = history.read_text(encoding="utf-8")
    assert "secret-token" not in text
    assert "document-body" not in text
    assert "raw-provider-response" not in text
    assert "Input validation failed" in text


def test_worker_registry_is_cleaned_before_restart(tmp_path: Path) -> None:
    manager = JobManager()
    project = tmp_path / "project"
    first = manager.enqueue("project", project, "first", lambda: {"first": True})
    assert manager.wait("project", project, first.job_id).state == "succeeded"
    for _ in range(100):
        if "project" not in manager._workers:
            break
        time.sleep(0.01)
    assert "project" not in manager._workers
    second = manager.enqueue("project", project, "second", lambda: {"second": True})
    assert manager.wait("project", project, second.job_id).state == "succeeded"


def test_gui_pages_security_project_upload_and_init_job(tmp_path: Path) -> None:
    app = create_app(registry_root=tmp_path / "registry")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for page in PAGES:
            page_response = client.get(f"/ui/{page}")
            assert page_response.status_code == 200
            assert 'id="root"' in page_response.text
            assert '/static/dist/app.js' in page_response.text
        shell = client.get("/ui/dashboard").text
        assert "Evidence Review Workspace" in shell
        assert "fonts.googleapis.com" not in shell
        assert "cdn.jsdelivr.net" not in shell
        assert "/static/data.js" not in shell
        bundle = client.get("/static/dist/app.js")
        assert bundle.status_code == 200
        assert "SI_DATA" not in bundle.text
        assert client.get("/static/dist/app.css").status_code == 200
        redirect = client.get(
            "/ui/analyze?project_id=project-one",
            follow_redirects=False,
        )
        assert redirect.status_code == 307
        assert redirect.headers["location"] == "/ui/impact-board?project_id=project-one"
        assert client.get("/", headers={"Host": "example.com"}).status_code == 403
        assert client.post("/api/projects", json={"path": str(tmp_path / "x")}).status_code == 403
        headers = _headers(client)
        assert (
            client.post(
                "/api/projects",
                headers={**headers, "Origin": "http://localhost"},
                json={"path": str(tmp_path / "x")},
            ).status_code
            == 403
        )
        response = client.post(
            "/api/projects",
            headers=headers,
            json={"path": str(tmp_path / "project"), "create": True},
        )
        project = response.json()["project"]
        assert response.status_code == 200
        assert client.get("/api/projects/not-registered/overview").status_code == 404
        upload = client.post(
            f"/api/projects/{project['project_id']}/uploads",
            headers=headers,
            json={
                "workflow": "change",
                "files": [
                    {
                        "filename": "change.md",
                        "content_base64": base64.b64encode(b"# Change").decode(),
                    }
                ],
            },
        )
        assert upload.status_code == 200
        response = client.post(
            f"/api/projects/{project['project_id']}/jobs",
            headers=headers,
            json={"action": "init"},
        )
        job_id = response.json()["job"]["job_id"]
        job = app.state.jobs.wait(project["project_id"], project["path"], job_id)
        assert job.state == "succeeded"
        history = Path(project["path"]) / ".specimpact" / "gui" / "jobs.jsonl"
        assert "OPENAI_API_KEY" not in history.read_text(encoding="utf-8")
        assert client.get(f"/api/projects/{project['project_id']}/overview").status_code == 200


def test_external_provider_requires_per_job_approval(tmp_path: Path) -> None:
    registry = ProjectRegistry(tmp_path / "registry")
    project = registry.create(tmp_path / "project")
    execute(project, "init", {})
    (Path(project.path) / "change.md").write_text("# Change", encoding="utf-8")
    execute(
        project,
        "llm_configure",
        {"provider": "ollama", "model": "remote", "base_url": "https://ollama.example.com"},
    )
    app = create_app(registry_root=tmp_path / "registry")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        headers = _headers(client)
        response = client.post(
            f"/api/projects/{project.project_id}/jobs",
            headers=headers,
            json={"action": "analyze", "params": {"path": "change.md"}},
        )
        assert response.status_code == 400
        assert "承認" in response.text


def test_external_preview_endpoint_receives_json_params(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "init", {})
    execute(project, "ingest", {"path": "docs", "aliases": "aliases.yml", "no_llm": True})
    execute(
        project,
        "llm_configure",
        {"provider": "ollama", "model": "remote", "base_url": "https://ollama.example.com"},
    )
    app = create_app(registry_root=tmp_path / "registry")
    params = quote(json.dumps({"path": "changes/change_credit_limit.md", "no_llm": True}))

    with TestClient(app, base_url="http://127.0.0.1") as client:
        preview = client.get(
            f"/api/projects/{project.project_id}/external-preview?action=analyze&params={params}"
        )

    assert preview.status_code == 200
    assert preview.json()["required"] is False


def test_analyze_external_preview_lists_extraction_and_rerank_counts(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "init", {})
    execute(project, "ingest", {"path": "docs", "aliases": "aliases.yml", "no_llm": True})
    execute(
        project,
        "llm_configure",
        {"provider": "ollama", "model": "remote", "base_url": "https://ollama.example.com"},
    )
    preview = external_preview(project, "analyze", {"path": "changes/change_credit_limit.md"})
    assert preview["required"] is True
    assert [
        (item["purpose"], item["item_count"]) for item in preview["transmissions"]
    ] == [
        ("変更要求からの entity 抽出", 1),
        ("候補 batch rerank", 13),
    ]
    rerank = preview["transmissions"][1]
    assert rerank["item_count_label"] == "13 以上（batch / 概算）"
    assert "semantic retrieval" in rerank["note"]


def test_codex_external_preview_requires_job_approval(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "init", {})
    execute(project, "ingest", {"path": "docs", "aliases": "aliases.yml", "no_llm": True})
    execute(project, "llm_configure", {"provider": "codex", "model": "gpt-test"})

    preview = external_preview(project, "analyze", {"path": "changes/change_credit_limit.md"})

    assert preview["required"] is True
    assert {item["provider"] for item in preview["transmissions"]} == {"codex"}


def test_dataset_tools_preview_external_transmissions_and_forward_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ProjectRegistry(tmp_path / "registry")
    project = registry.create(tmp_path / "project")
    execute(project, "init", {})
    execute(
        project,
        "llm_configure",
        {"provider": "ollama", "model": "remote", "base_url": "https://ollama.example.com"},
    )
    (Path(project.path) / "dataset.yml").write_text(
        "cases:\n  - case_id: one\n  - case_id: two\n",
        encoding="utf-8",
    )
    calls = []

    def fake_tool(store, path, **kwargs):
        calls.append((path.name, kwargs))
        return {"ok": True}

    monkeypatch.setattr("specimpact.webui.services.evaluate_dataset", fake_tool)
    monkeypatch.setattr("specimpact.webui.services.release_validate", fake_tool)

    for action in ("eval", "release_check"):
        params = {"dataset": "dataset.yml"}
        preview = external_preview(project, action, params)
        assert preview["required"] is True
        assert preview["transmissions"][0]["item_count"] == 2
        assert preview["transmissions"][1]["item_count_label"] == "解析時に確定（対象 change: 2）"
        assert "semantic retrieval" in preview["transmissions"][1]["note"]
        execute(project, action, {**params, "external_approved": True})

    assert len(calls) == 2
    assert all(call[1]["yes"] is True for call in calls)
    assert all(call[1]["confirm"]("approve") is True for call in calls)


def test_evaluate_dataset_forwards_consent_to_internal_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    change = tmp_path / "change.md"
    expected = tmp_path / "expected.json"
    manifest = tmp_path / "dataset.yml"
    change.write_text("# Change", encoding="utf-8")
    expected.write_text("{}", encoding="utf-8")
    manifest.write_text(
        "cases:\n"
        "  - case_id: one\n"
        "    category: evaluation\n"
        "    change: change.md\n"
        "    expected: expected.json\n",
        encoding="utf-8",
    )
    calls = []

    def fake_analyze(case_store, change_path, **kwargs):
        calls.append((case_store, change_path, kwargs))

    def confirm(_message: str) -> bool:
        return True

    monkeypatch.setattr("specimpact.core.analyze_change", fake_analyze)
    monkeypatch.setattr("specimpact.operations.evaluate_latest", lambda *_args: {})

    result = evaluate_dataset(store, manifest, yes=True, no_llm=True, confirm=confirm)

    assert result["case_count"] == 1
    assert calls[0][1] == change
    assert calls[0][2] == {"yes": True, "no_llm": True, "confirm": confirm}


def test_report_data_includes_all_evidence_quotes_and_locations(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "demo_run", {})
    report = report_data(project)
    candidate = next(item for item in report["must_review"] if item["evidence_ids"])
    assert len(candidate["evidence"]) == len(candidate["evidence_ids"])
    assert all(item["quote"] for item in candidate["evidence"])
    assert all(item["source_location"]["file"] for item in candidate["evidence"])


def test_design_documents_data_highlights_latest_report_evidence(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "demo_run", {})

    data = design_documents_data(project)

    assert data["selected_evidence_ids"]
    assert any(item["highlight_count"] > 0 for item in data["documents"])
    assert any(
        row["highlight"]
        for document in data["documents"]
        for row in document["rows"]
    )


def test_design_documents_endpoint_filters_to_selected_evidence(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    copy_demo(demo_source(), target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    execute(project, "demo_run", {})
    evidence_id = design_documents_data(project)["selected_evidence_ids"][0]
    app = create_app(registry_root=tmp_path / "registry")

    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(
            f"/api/projects/{project.project_id}/design-documents",
            params={"evidence_id": evidence_id},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["selected_evidence_ids"] == [evidence_id]
    assert any(document["highlight_count"] for document in body["documents"])


def test_source_library_summarizes_managed_ingest_and_endpoint(tmp_path: Path) -> None:
    project = ProjectRegistry(tmp_path / "registry").create(tmp_path / "project")
    execute(project, "init", {})
    uploaded = save_uploads(
        project.path,
        "docs",
        [
            (
                "screen.md",
                "# 申込画面\n\n## Fields\n- 希望利用限度額\n\n## Calls\n- 申込API".encode(),
            ),
            (
                "api.md",
                "# 申込API\n\n## Request fields\n- requestedCreditLimit".encode(),
            ),
        ],
    )
    execute(project, "ingest", {"path": str(uploaded[0].parent), "no_llm": True})

    summary = source_library_data(project)
    assert len(summary["sources"]) == 2
    assert {item["title"] for item in summary["sources"]} == {"申込画面", "申込API"}
    assert all(item["status"] == "ready" for item in summary["sources"])
    assert all(item["evidence_count"] > 0 for item in summary["sources"])

    app = create_app(registry_root=tmp_path / "registry")
    with TestClient(app, base_url="http://127.0.0.1") as client:
        response = client.get(f"/api/projects/{project.project_id}/sources")
        redirect = client.get(
            f"/ui/ingest?project_id={project.project_id}",
            follow_redirects=False,
        )
    assert response.status_code == 200
    assert len(response.json()["sources"]) == 2
    assert redirect.headers["location"] == f"/ui/sources?project_id={project.project_id}"


def test_session_tokens_are_bounded_and_expire(tmp_path: Path) -> None:
    app = create_app(registry_root=tmp_path / "registry", max_sessions=4)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for _ in range(10):
            client.cookies.clear()
            client.get("/api/session")
        assert len(app.state.sessions) == 4
        token = client.get("/api/session").json()["csrf_token"]
        app.state.sessions[token] = 0
        response = client.post(
            "/api/projects",
            headers={"Origin": "http://127.0.0.1", "X-CSRF-Token": token},
            json={"path": str(tmp_path / "project"), "create": True},
        )
        assert response.status_code == 403


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_sessions": 0},
        {"max_sessions": -1},
        {"session_ttl_seconds": 0},
        {"session_ttl_seconds": -1},
    ],
)
def test_session_settings_must_be_positive(tmp_path: Path, kwargs: dict) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        create_app(registry_root=tmp_path / "registry", **kwargs)


def test_guided_demo_is_copied_and_generates_local_candidates(tmp_path: Path) -> None:
    source = Path("examples/credit_card_enrollment")
    digest = _tree_digest(source)
    target = tmp_path / "demo"
    copy_demo(source, target)
    project = ProjectRegistry(tmp_path / "registry").add(target)
    result = execute(project, "demo_run", {})
    assert result["result"]["candidates"] == 13
    assert _tree_digest(source) == digest
    graph = graph_data(project)
    assert graph["nodes"]
    assert graph["edges"]
    store = Path(project.path) / ".specimpact"
    assert _lines(store / "artifacts.jsonl", Artifact)
    assert _lines(store / "entities.jsonl", Entity)
    assert _lines(store / "relations.jsonl", Relation)
    assert _lines(store / "evidence.jsonl", Evidence)


def test_packaged_demo_matches_repository_sample() -> None:
    assert _tree_digest(Path("examples/credit_card_enrollment")) == _resource_tree_digest(
        demo_source()
    )


def _headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/session").json()["csrf_token"]
    return {"Origin": "http://127.0.0.1", "X-CSRF-Token": token}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _resource_tree_digest(root, prefix: str = "") -> str:
    digest = hashlib.sha256()
    files = []

    def collect(current, current_prefix: str) -> None:
        for item in current.iterdir():
            relative = f"{current_prefix}/{item.name}".lstrip("/")
            if item.is_dir():
                collect(item, relative)
            else:
                files.append((relative, item))

    collect(root, prefix)
    for relative, item in sorted(files):
        digest.update(relative.encode())
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _lines(path: Path, model) -> list:
    return [
        model.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
