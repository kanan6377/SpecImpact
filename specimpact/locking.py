"""Process locking shared by ingestion, application and analysis storage."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from types import TracebackType

_local_locks = threading.local()


class ProjectWriteLock:
    """Small cross-platform process lock backed by `.specimpact/write.lock`."""

    def __init__(self, store_root: Path | str, *, timeout: float = 30.0) -> None:
        self.path = Path(store_root) / "write.lock"
        self.timeout = timeout
        self._handle = None
        self._nested = False
        self._key = str(self.path.resolve())

    def __enter__(self) -> ProjectWriteLock:
        held = getattr(_local_locks, "held", {})
        _local_locks.held = held
        if held.get(self._key, 0):
            held[self._key] += 1
            self._nested = True
            return self
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
                held[self._key] = 1
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
        held = getattr(_local_locks, "held", {})
        if self._nested:
            held[self._key] -= 1
            self._nested = False
            return
        if self._handle is None:
            return
        try:
            self._release()
        finally:
            self._handle.close()
            self._handle = None
            held.pop(self._key, None)

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
