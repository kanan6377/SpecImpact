from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Project(BaseModel):
    project_id: str
    display_name: str
    path: str
    last_used_at: str


def project_id_for(path: Path | str) -> str:
    resolved = str(Path(path).expanduser().resolve())
    return hashlib.sha256(os.path.normcase(resolved).encode("utf-8")).hexdigest()[:16]


def project_from_path(path: Path | str) -> Project:
    resolved = Path(path).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError(f"Project directory does not exist: {resolved}")
    return Project(
        project_id=project_id_for(resolved),
        display_name=resolved.name or str(resolved),
        path=str(resolved),
        last_used_at=utc_now(),
    )


class HostContext(BaseModel):
    host: str = "unknown"
    workspace_root: str
    project_id: str
    session_id: str | None = None
    model: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    external: bool = True


class TransmissionPreview(BaseModel):
    preview_id: str
    project_id: str
    purpose: str
    host: str
    provider: str | None = None
    model: str | None = None
    external: bool
    required: bool
    item_count: int
    redacted: bool
    source_hash: str
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    expires_at: str


class ApprovalGrant(BaseModel):
    grant_id: str
    token: str
    preview_id: str
    project_id: str
    purpose: str
    source_hash: str
    created_at: str = Field(default_factory=utc_now)
    expires_at: str
    used_at: str | None = None


class PreparedContext(BaseModel):
    context_id: str
    project_id: str
    purpose: str
    schema_name: str
    instructions: str
    payload: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    source_hash: str
    transmission_preview: TransmissionPreview | None = None
    created_at: str = Field(default_factory=utc_now)


class JobHandle(BaseModel):
    job_id: str
    project_id: str
    action: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: str
    updated_at: str
    progress: int | None = Field(default=None, ge=0, le=100)
    message: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None


class ChangeSessionView(BaseModel):
    session_id: str
    project_id: str
    change_id: str
    title: str
    status: str
    change_atoms: list[dict[str, Any]] = Field(default_factory=list)
    impacts: list[dict[str, Any]] = Field(default_factory=list)
    decisions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


PUBLIC_CONTRACTS = (
    HostContext,
    PreparedContext,
    TransmissionPreview,
    ApprovalGrant,
    JobHandle,
    ChangeSessionView,
)


def public_contract_schemas() -> dict[str, dict[str, Any]]:
    return {model.__name__: model.model_json_schema() for model in PUBLIC_CONTRACTS}
