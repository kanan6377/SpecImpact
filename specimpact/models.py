from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Document(BaseModel):
    document_id: str
    path: str
    title: str
    document_type: str = "design_document"
    hash: str
    loaded_at: str = Field(default_factory=utc_now)


class Section(BaseModel):
    section_id: str
    document_id: str
    heading: str
    level: int
    line_start: int
    line_end: int


class Chunk(BaseModel):
    chunk_id: str
    document_id: str
    section_id: str
    text: str
    line_start: int
    line_end: int


class Artifact(BaseModel):
    artifact_id: str
    artifact_type: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(default_factory=list)
    extraction_methods: list[str] = Field(default_factory=list)


class Entity(BaseModel):
    entity_id: str
    entity_type: str
    display_name: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    source_document_ids: list[str] = Field(default_factory=list)
    extraction_methods: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    relation_id: str
    relation_type: str
    source_id: str
    target_id: str
    evidence_ids: list[str]
    extraction_method: str = "rule"
    polarity: str = "explicit"
    status: str = "unconfirmed"
    match_type: str = "exact"
    source_document_ids: list[str] = Field(default_factory=list)


class EvidenceSupport(BaseModel):
    type: str
    id: str


class SourceLocation(BaseModel):
    file: str
    line_start: int
    line_end: int


class Evidence(BaseModel):
    evidence_id: str
    document_id: str
    section_id: str
    chunk_id: str
    quote: str
    evidence_type: str
    supports: list[EvidenceSupport]
    source_location: SourceLocation


class Impact(BaseModel):
    artifact_id: str
    display_name: str
    artifact_type: str
    review_priority: str
    evidence_strength: str
    match_type: str
    relation_distance: int
    rule_assessment: str
    reason: str
    relation_paths: list[str]
    evidence_ids: list[str]
    relation_statuses: list[str] = Field(default_factory=list)
    needs_review: bool
    llm_judgement: str | None = None
    llm_reason: str | None = None
    selected_evidence_ids: list[str] | None = None
    impact_type: str | None = None
    required_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uncertainty: str | None = None


class ChangeRequest(BaseModel):
    change_id: str
    title: str
    path: str
    body: str
    changed_entity_ids: list[str]


class Report(BaseModel):
    run_id: str
    change: ChangeRequest
    impacts: list[Impact]

    def grouped(self) -> dict[str, list[dict[str, Any]]]:
        groups = {name: [] for name in ("must_review", "should_review", "may_review", "hidden")}
        for impact in self.impacts:
            groups[impact.review_priority].append(impact.model_dump(exclude_none=True))
        return groups
