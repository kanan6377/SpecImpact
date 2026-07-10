from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specimpact.application.contracts import utc_now
from specimpact.application.security import ProjectWriteLock
from specimpact.store import LocalStore


class MutationCoordinator:
    def __init__(self, store: LocalStore) -> None:
        self.store = store
        self.path = store.root / "idempotency.jsonl"

    def run(
        self,
        *,
        idempotency_key: str,
        action: str,
        params: dict[str, Any],
        operation: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        key = idempotency_key.strip()
        if not key or len(key) > 200:
            raise ValueError("A non-empty idempotency key of at most 200 characters is required")
        key_hash = _hash_text(key)
        params_hash = _hash_json(params)
        with ProjectWriteLock(self.store.root):
            records = _read_records(self.path)
            previous = next((item for item in records if item["key_hash"] == key_hash), None)
            if previous:
                if previous["action"] != action or previous["params_hash"] != params_hash:
                    raise ValueError("Idempotency key was already used with different parameters")
                return previous["result"]
            result = operation()
            records.append(
                {
                    "key_hash": key_hash,
                    "action": action,
                    "params_hash": params_hash,
                    "created_at": utc_now(),
                    "result": result,
                }
            )
            _write_records(self.store, self.path, records)
            return result


def _hash_json(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _hash_text(serialized)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_records(store: LocalStore, path: Path, records: list[dict[str, Any]]) -> None:
    content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
    store.write_text(path, content)
