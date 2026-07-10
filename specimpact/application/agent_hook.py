from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from specimpact.application.contracts import utc_now
from specimpact.application.security import ProjectWriteLock, WorkspaceBoundary
from specimpact.store import LocalStore

DESIGN_SUFFIXES = {".xlsx", ".xls", ".csv", ".md", ".txt", ".yaml", ".yml", ".json", ".sql"}
PATH_KEYS = {"path", "file", "file_path", "target_file", "target_path"}


def handle_agent_hook(
    project_path: Path | str,
    *,
    host: str,
    event: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    root = Path(project_path).expanduser().resolve()
    store = LocalStore(root / ".specimpact")
    if event not in {"post-tool-use", "postToolUse"} or not (store.root / "config.yml").is_file():
        return {}
    boundary = WorkspaceBoundary(root)
    notifications = []
    for value in _path_values(payload):
        try:
            path = boundary.resolve(value)
        except ValueError:
            continue
        if not path.is_file() or path.suffix.lower() not in DESIGN_SUFFIXES:
            continue
        notifications.append(
            {
                "event": "source_change_detected",
                "host": host,
                "path": path.relative_to(root).as_posix(),
                "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
                "created_at": utc_now(),
            }
        )
    if notifications:
        ledger = store.root / "host_change_notifications.jsonl"
        with ProjectWriteLock(store.root):
            existing = ledger.read_text(encoding="utf-8") if ledger.exists() else ""
            rows = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in notifications)
            store.write_text(ledger, existing + rows)
    return {}


def _path_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        result = [
            item
            for key, item in value.items()
            if str(key).lower() in PATH_KEYS and isinstance(item, str)
        ]
        for item in value.values():
            result.extend(_path_values(item))
        return result
    if isinstance(value, list):
        return [path for item in value for path in _path_values(item)]
    return []
