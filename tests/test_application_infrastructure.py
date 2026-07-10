from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

from specimpact.application.jobs import Job, JobManager
from specimpact.application.mutations import MutationCoordinator
from specimpact.application.security import ProjectWriteLock, WorkspaceBoundary
from specimpact.store import LocalStore


def _hold_project_write_lock(
    store_root: str,
    ready: multiprocessing.queues.Queue[str],
    release: multiprocessing.synchronize.Event,
) -> None:
    with ProjectWriteLock(store_root, timeout=2):
        ready.put("locked")
        release.wait(timeout=5)


def test_workspace_boundary_rejects_paths_outside_workspace_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    boundary = WorkspaceBoundary(workspace)

    with pytest.raises(ValueError, match="escapes workspace root"):
        boundary.resolve(outside)


def test_workspace_boundary_rejects_symlink_escaping_workspace_root(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    escape_link = workspace / "escape.md"
    try:
        escape_link.symlink_to(outside)
    except OSError as error:
        pytest.skip(f"Symlink creation is unavailable in this environment: {error}")

    with pytest.raises(ValueError, match="escapes workspace root"):
        WorkspaceBoundary(workspace).resolve(escape_link)


def test_mutation_coordinator_replays_requests_and_hashes_key(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "workspace" / ".specimpact")
    coordinator = MutationCoordinator(store)
    raw_key = "mutation-key-that-must-not-be-persisted"
    calls = 0

    def operation() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"call": calls}

    first = coordinator.run(
        idempotency_key=raw_key,
        action="ingest",
        params={"source": "requirements.md", "force": False},
        operation=operation,
    )
    replay = coordinator.run(
        idempotency_key=raw_key,
        action="ingest",
        params={"force": False, "source": "requirements.md"},
        operation=operation,
    )

    assert first == replay == {"call": 1}
    assert calls == 1
    with pytest.raises(ValueError, match="different parameters"):
        coordinator.run(
            idempotency_key=raw_key,
            action="ingest",
            params={"source": "other.md", "force": False},
            operation=operation,
        )

    ledger = json.loads(coordinator.path.read_text(encoding="utf-8"))
    assert ledger["key_hash"] != raw_key
    assert raw_key not in coordinator.path.read_text(encoding="utf-8")
    assert "idempotency_key" not in ledger


def test_project_write_lock_excludes_a_separate_process(tmp_path: Path) -> None:
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    release = context.Event()
    store_root = tmp_path / ".specimpact"
    process = context.Process(
        target=_hold_project_write_lock,
        args=(str(store_root), ready, release),
    )
    process.start()
    try:
        assert ready.get(timeout=5) == "locked"
        with pytest.raises(TimeoutError, match="Timed out waiting for project write lock"):
            with ProjectWriteLock(store_root, timeout=0.1):
                pass
    finally:
        release.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    assert process.exitcode == 0


def test_job_manager_migrates_legacy_ledger_without_removing_it(tmp_path: Path) -> None:
    project = tmp_path / "project"
    legacy_path = project / ".specimpact" / "gui" / "jobs.jsonl"
    legacy_path.parent.mkdir(parents=True)
    legacy_job = Job(project_id="project-1", action="legacy", state="succeeded")
    legacy_content = json.dumps(legacy_job.model_dump()) + "\n"
    legacy_path.write_text(legacy_content, encoding="utf-8")

    jobs = JobManager().list("project-1", project)
    canonical_path = project / ".specimpact" / "jobs.jsonl"

    assert [job.job_id for job in jobs] == [legacy_job.job_id]
    assert canonical_path.read_text(encoding="utf-8") == legacy_content
    assert legacy_path.read_text(encoding="utf-8") == legacy_content


def test_job_manager_replays_idempotent_enqueue_and_rejects_action_change(tmp_path: Path) -> None:
    manager = JobManager()
    project = tmp_path / "project"
    calls = 0

    def runner() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"call": calls}

    first = manager.enqueue(
        "project-1",
        project,
        "ingest",
        runner,
        idempotency_key="job-key",
    )
    replay = manager.enqueue(
        "project-1",
        project,
        "ingest",
        runner,
        idempotency_key="job-key",
    )

    assert replay.job_id == first.job_id
    assert manager.wait("project-1", project, first.job_id).state == "succeeded"
    assert calls == 1
    with pytest.raises(ValueError, match="another job action"):
        manager.enqueue(
            "project-1",
            project,
            "analyze",
            runner,
            idempotency_key="job-key",
        )
