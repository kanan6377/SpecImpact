from __future__ import annotations

import os
import time
from pathlib import Path
from types import TracebackType


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


class ProjectWriteLock:
    """Small cross-platform process lock backed by `.specimpact/write.lock`."""

    def __init__(self, store_root: Path | str, *, timeout: float = 30.0) -> None:
        self.path = Path(store_root) / "write.lock"
        self.timeout = timeout
        self._handle = None

    def __enter__(self) -> ProjectWriteLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+b")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"\0")
            self._handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._acquire()
                return self
            except OSError as error:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise TimeoutError(
                        f"Timed out waiting for project write lock: {self.path}"
                    ) from error
                time.sleep(0.05)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is None:
            return
        try:
            self._release()
        finally:
            self._handle.close()
            self._handle = None

    def _acquire(self) -> None:
        assert self._handle is not None
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(self) -> None:
        assert self._handle is not None
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
