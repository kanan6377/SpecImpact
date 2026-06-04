from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Project(BaseModel):
    project_id: str
    display_name: str
    path: str
    last_used_at: str


class ProjectRegistry:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or Path.home() / ".specimpact-gui").expanduser()
        self.path = self.root / "projects.json"
        self._lock = threading.RLock()

    def list(self) -> list[Project]:
        with self._lock:
            projects = [Project.model_validate(item) for item in self._read()]
            return sorted(projects, key=lambda item: item.last_used_at, reverse=True)

    def add(
        self,
        path: Path | str,
        *,
        display_name: str | None = None,
        create: bool = False,
    ) -> Project:
        with self._lock:
            resolved = Path(path).expanduser().resolve()
            if create:
                resolved.mkdir(parents=True, exist_ok=True)
            if not resolved.is_dir():
                raise ValueError(f"Project directory does not exist: {resolved}")
            project_id = self.project_id_for(resolved)
            projects = self.list()
            existing = next((item for item in projects if item.project_id == project_id), None)
            if existing:
                existing.last_used_at = utc_now()
                if display_name:
                    existing.display_name = display_name.strip() or existing.display_name
                self._write([item.model_dump() for item in projects])
                return existing
            project = Project(
                project_id=project_id,
                display_name=(display_name or resolved.name or str(resolved)).strip(),
                path=str(resolved),
                last_used_at=utc_now(),
            )
            self._write([item.model_dump() for item in [*projects, project]])
            return project

    def create(self, path: Path | str, *, display_name: str | None = None) -> Project:
        return self.add(path, display_name=display_name, create=True)

    def get(self, project_id: str, *, touch: bool = False) -> Project:
        with self._lock:
            projects = self.list()
            project = next((item for item in projects if item.project_id == project_id), None)
            if not project:
                raise KeyError(f"Unknown project: {project_id}")
            if touch:
                project.last_used_at = utc_now()
                self._write([item.model_dump() for item in projects])
            return project

    def remove(self, project_id: str) -> None:
        with self._lock:
            projects = self.list()
            if not any(item.project_id == project_id for item in projects):
                raise KeyError(f"Unknown project: {project_id}")
            self._write([item.model_dump() for item in projects if item.project_id != project_id])

    @staticmethod
    def project_id_for(path: Path | str) -> str:
        resolved = str(Path(path).expanduser().resolve())
        normalized = os.path.normcase(resolved)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise ValueError("Invalid GUI project registry") from error
        if not isinstance(value, list):
            raise ValueError("GUI project registry must contain a list")
        return value

    def _write(self, projects: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=".projects.", dir=self.root, text=True)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as temp:
                json.dump(projects, temp, ensure_ascii=False, indent=2)
                temp.write("\n")
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
