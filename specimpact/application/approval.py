from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from specimpact.application.contracts import ApprovalGrant, Project, TransmissionPreview, utc_now
from specimpact.application.security import ProjectWriteLock
from specimpact.graphrag import redact_payload
from specimpact.store import LocalStore

GRANT_TTL_MINUTES = 10


class ApprovalManager:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.store_root = Path(project.path) / ".specimpact"
        self.store = LocalStore(self.store_root)
        self.grant_path = self.store_root / "approval_grants.jsonl"

    def create_preview(
        self,
        *,
        purpose: str,
        host: str,
        payload: Any,
        evidence_ids: list[str] | None = None,
        provider: str | None = None,
        model: str | None = None,
        external: bool = True,
    ) -> TransmissionPreview:
        now = datetime.now(timezone.utc)
        preview = TransmissionPreview(
            preview_id=f"preview-{uuid4().hex}",
            project_id=self.project.project_id,
            purpose=purpose,
            host=host,
            provider=provider,
            model=model,
            external=external,
            required=external,
            item_count=_item_count(payload),
            redacted=redact_payload(payload) != payload,
            source_hash=_payload_hash(payload),
            evidence_ids=sorted(set(evidence_ids or [])),
            created_at=now.isoformat(),
            expires_at=(now + timedelta(minutes=GRANT_TTL_MINUTES)).isoformat(),
        )
        with ProjectWriteLock(self.store_root):
            previews = self.store.read("transmission_previews", TransmissionPreview)
            previews.append(preview)
            self.store.write("transmission_previews", previews)
        return preview

    def issue_grant(
        self,
        preview_id: str,
        *,
        decision: Literal["approve"],
    ) -> ApprovalGrant:
        if decision != "approve":
            raise ValueError("Transmission was not approved")
        with ProjectWriteLock(self.store_root):
            preview = self._get_preview(preview_id)
            _require_unexpired(preview.expires_at, "Transmission preview expired")
            token = secrets.token_urlsafe(32)
            grant = ApprovalGrant(
                grant_id=f"grant-{uuid4().hex}",
                token=token,
                preview_id=preview.preview_id,
                project_id=preview.project_id,
                purpose=preview.purpose,
                source_hash=preview.source_hash,
                expires_at=preview.expires_at,
            )
            records = self._read_grants()
            if any(item.get("preview_id") == preview.preview_id for item in records):
                raise ValueError("An approval grant was already issued for this preview")
            records.append(
                {
                    **grant.model_dump(exclude={"token"}),
                    "token_hash": _token_hash(token),
                }
            )
            self._write_grants(records)
            return grant

    def consume(self, token: str, *, purpose: str, source_hash: str) -> str:
        with ProjectWriteLock(self.store_root):
            records = self._read_grants()
            record = next(
                (item for item in records if item.get("token_hash") == _token_hash(token)),
                None,
            )
            if not record:
                raise ValueError("Unknown approval grant")
            if record["project_id"] != self.project.project_id:
                raise ValueError("Approval grant belongs to another project")
            if record["purpose"] != purpose or record["source_hash"] != source_hash:
                raise ValueError("Approval grant does not match this transmission")
            if record.get("used_at"):
                raise ValueError("Approval grant was already used")
            _require_unexpired(record["expires_at"], "Approval grant expired")
            record["used_at"] = utc_now()
            self._write_grants(records)
            return record["grant_id"]

    def get_preview(self, preview_id: str) -> TransmissionPreview:
        return self._get_preview(preview_id)

    def _get_preview(self, preview_id: str) -> TransmissionPreview:
        preview = next(
            (
                item
                for item in self.store.read("transmission_previews", TransmissionPreview)
                if item.preview_id == preview_id
            ),
            None,
        )
        if not preview:
            raise KeyError(f"Unknown transmission preview: {preview_id}")
        return preview

    def _read_grants(self) -> list[dict[str, Any]]:
        if not self.grant_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.grant_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _write_grants(self, records: list[dict[str, Any]]) -> None:
        content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
        self.store.write_text(self.grant_path, content)


def _payload_hash(payload: Any) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _item_count(payload: Any) -> int:
    if isinstance(payload, (list, tuple, set)):
        return len(payload)
    if isinstance(payload, dict):
        for key in ("items", "evidence", "chunks", "cells", "regions"):
            if isinstance(payload.get(key), list):
                return len(payload[key])
    return 1


def _require_unexpired(value: str, message: str) -> None:
    if datetime.fromisoformat(value) <= datetime.now(timezone.utc):
        raise ValueError(message)
