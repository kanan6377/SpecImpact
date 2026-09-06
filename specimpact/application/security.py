from __future__ import annotations

from pathlib import Path

from specimpact.locking import ProjectWriteLock as ProjectWriteLock


class WorkspaceBoundary:
    def __init__(self, workspace_root: Path | str) -> None:
        self.root = Path(workspace_root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError(f"Workspace root is not a directory: {self.root}")

    def resolve(self, value: Path | str, *, must_exist: bool = True) -> Path:
        raw = Path(value).expanduser()
        candidate = raw if raw.is_absolute() else self.root / raw
        try:
            resolved = candidate.resolve(strict=must_exist)
        except OSError as error:
            raise ValueError(f"Workspace path cannot be resolved: {value}") from error
        if not resolved.is_relative_to(self.root):
            raise ValueError(f"Path escapes workspace root: {value}")
        return resolved
