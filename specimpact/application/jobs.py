from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel, Field

from specimpact.application.contracts import JobHandle
from specimpact.application.security import ProjectWriteLock

Runner = Callable[[], dict[str, Any] | str | None]
TERMINAL_STATES = {"succeeded", "failed", "cancelled", "interrupted"}
INPUT_KINDS = {"path", "upload", "demo", "settings"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: uuid4().hex)
    project_id: str
    action: str
    state: str = "queued"
    input_kind: str = "path"
    created_at: str = Field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    result_summary: dict[str, Any] | str | None = None
    error_summary: str | None = None
    idempotency_key_hash: str | None = None


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._jobs: dict[str, list[Job]] = defaultdict(list)
        self._paths: dict[str, Path] = {}
        self._queues: dict[str, deque[tuple[Job, Runner]]] = defaultdict(deque)
        self._workers: dict[str, threading.Thread] = {}

    def register_project(self, project_id: str, project_path: Path | str) -> None:
        with self._lock:
            store_root = Path(project_path) / ".specimpact"
            path = store_root / "jobs.jsonl"
            legacy_path = store_root / "gui" / "jobs.jsonl"
            if project_id in self._paths:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            if legacy_path.exists() and (
                not path.exists() or legacy_path.stat().st_mtime_ns > path.stat().st_mtime_ns
            ):
                shutil.copy2(legacy_path, path)
            self._paths[project_id] = path
            jobs = self._read(path)
            changed = False
            for job in jobs:
                if job.state in {"queued", "running"}:
                    job.state = "interrupted"
                    job.finished_at = utc_now()
                    job.error_summary = "Server restarted before this job completed."
                    changed = True
            self._jobs[project_id] = jobs
            if changed:
                self._persist(project_id)

    def enqueue(
        self,
        project_id: str,
        project_path: Path | str,
        action: str,
        runner: Runner,
        *,
        input_kind: str = "path",
        idempotency_key: str | None = None,
    ) -> Job:
        self.register_project(project_id, project_path)
        if input_kind not in INPUT_KINDS:
            raise ValueError("Unknown job input kind")
        with self._condition:
            key_hash = _idempotency_hash(idempotency_key) if idempotency_key else None
            if key_hash:
                existing = next(
                    (
                        item
                        for item in self._jobs[project_id]
                        if item.idempotency_key_hash == key_hash
                    ),
                    None,
                )
                if existing:
                    if existing.action != action:
                        raise ValueError("Idempotency key was already used for another job action")
                    return existing.model_copy(deep=True)
            job = Job(
                project_id=project_id,
                action=action,
                input_kind=input_kind,
                idempotency_key_hash=key_hash,
            )
            self._jobs[project_id].append(job)
            self._queues[project_id].append((job, runner))
            self._persist(project_id)
            self._ensure_worker(project_id)
            self._condition.notify_all()
            return job

    def list(self, project_id: str, project_path: Path | str) -> list[Job]:
        self.register_project(project_id, project_path)
        with self._lock:
            return [item.model_copy(deep=True) for item in reversed(self._jobs[project_id])]

    def get(self, project_id: str, project_path: Path | str, job_id: str) -> Job:
        jobs = self.list(project_id, project_path)
        job = next((item for item in jobs if item.job_id == job_id), None)
        if not job:
            raise KeyError(f"Unknown job: {job_id}")
        return job

    def cancel(self, project_id: str, project_path: Path | str, job_id: str) -> Job:
        self.register_project(project_id, project_path)
        with self._condition:
            job = next((item for item in self._jobs[project_id] if item.job_id == job_id), None)
            if not job:
                raise KeyError(f"Unknown job: {job_id}")
            if job.state != "queued":
                raise ValueError("Only queued jobs can be cancelled")
            job.state = "cancelled"
            job.finished_at = utc_now()
            self._persist(project_id)
            self._condition.notify_all()
            return job.model_copy(deep=True)

    def wait(
        self,
        project_id: str,
        project_path: Path | str,
        job_id: str,
        timeout: float = 10,
    ) -> Job:
        self.register_project(project_id, project_path)
        with self._condition:
            self._condition.wait_for(
                lambda: self.get(project_id, project_path, job_id).state in TERMINAL_STATES,
                timeout=timeout,
            )
        return self.get(project_id, project_path, job_id)

    def _ensure_worker(self, project_id: str) -> None:
        if project_id in self._workers:
            return
        worker = threading.Thread(
            target=self._work,
            args=(project_id,),
            name=f"specimpact-gui-{project_id}",
            daemon=True,
        )
        self._workers[project_id] = worker
        worker.start()

    def _work(self, project_id: str) -> None:
        while True:
            with self._condition:
                queue = self._queues[project_id]
                while queue and queue[0][0].state == "cancelled":
                    queue.popleft()
                if not queue:
                    self._workers.pop(project_id, None)
                    return
                job, runner = queue.popleft()
                if job.state != "queued":
                    continue
                job.state = "running"
                job.started_at = utc_now()
                self._persist(project_id)
                self._condition.notify_all()
            try:
                result = runner()
            except Exception as error:  # noqa: BLE001 - errors are summarized for GUI display
                with self._condition:
                    job.state = "failed"
                    job.error_summary = _safe_error(error)
                    job.finished_at = utc_now()
                    self._persist(project_id)
                    self._condition.notify_all()
            else:
                with self._condition:
                    job.state = "succeeded"
                    job.result_summary = result
                    job.finished_at = utc_now()
                    self._persist(project_id)
                    self._condition.notify_all()

    def _persist(self, project_id: str) -> None:
        path = self._paths[project_id]
        path.parent.mkdir(parents=True, exist_ok=True)
        with ProjectWriteLock(path.parent):
            persisted = {item.job_id: item for item in self._read(path)}
            persisted.update({item.job_id: item for item in self._jobs[project_id]})
            jobs = sorted(persisted.values(), key=lambda item: item.created_at)
            content = "".join(
                json.dumps(job.model_dump(), ensure_ascii=False) + "\n" for job in jobs
            )
            _atomic_write(path, content)
            # v1.2 compatibility mirror; the canonical ledger is `.specimpact/jobs.jsonl`.
            legacy_path = path.parent / "gui" / "jobs.jsonl"
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(legacy_path, content)

    @staticmethod
    def _read(path: Path) -> list[Job]:
        if not path.exists():
            return []
        return [
            Job.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]


def _safe_error(error: Exception) -> str:
    if isinstance(error, ValueError):
        return "Input validation failed. Review the submitted paths and options."
    if isinstance(error, OSError):
        return "Local file operation failed. Review project permissions and paths."
    return "Unexpected job failure. Review the server diagnostics."


def job_handle(job: Job) -> JobHandle:
    status = "failed" if job.state == "interrupted" else job.state
    result = job.result_summary if isinstance(job.result_summary, dict) else None
    message = job.result_summary if isinstance(job.result_summary, str) else None
    return JobHandle(
        job_id=job.job_id,
        project_id=job.project_id,
        action=job.action,
        status=status,
        created_at=job.created_at,
        updated_at=job.finished_at or job.started_at or job.created_at,
        message=message,
        result=result,
        error=job.error_summary,
    )


def _idempotency_hash(value: str) -> str:
    import hashlib

    key = value.strip()
    if not key or len(key) > 200:
        raise ValueError("Invalid idempotency key")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    handle, temp_name = tempfile.mkstemp(prefix=".jobs.", dir=path.parent, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as temp:
            temp.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
