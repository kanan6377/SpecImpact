from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

LengthUnit = Literal["characters", "bytes", "unknown"]


def content_id(prefix: str, value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}.{hashlib.sha256(encoded.encode()).hexdigest()}"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceAnchor(Contract):
    evidence_id: str
    document_id: str
    source_hash: str
    quote_hash: str
    file: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    sheet: str | None = None
    cells: list[str] = Field(default_factory=list)


class Mention(Contract):
    mention_id: str
    text: str
    entity_id: str
    scope: str = ""
    anchor: SourceAnchor


class IdentityAssertion(Contract):
    left_id: str
    right_id: str
    scope: str
    relation: Literal["same", "related", "different", "unsure"]
    evidence_ids: list[str] = Field(min_length=1)
    status: Literal["unconfirmed", "confirmed", "rejected"] = "unconfirmed"


class LengthValue(Contract):
    value: StrictInt = Field(ge=0)
    unit: LengthUnit = "unknown"


class SpecAssertion(Contract):
    assertion_id: str
    subject_id: str
    artifact_id: str
    scope: str = ""
    property: Literal["max_length"] = "max_length"
    value: LengthValue
    conditions: list[str] = Field(default_factory=list)
    anchor: SourceAnchor
    extraction_method: Literal["labelled_text", "labelled_table"]
    status: Literal["unconfirmed", "confirmed", "rejected"] = "unconfirmed"


class ChangeOperation(Contract):
    operation_id: str
    change_id: str
    target_terms: list[str] = Field(min_length=1)
    scope: str = ""
    property: str
    before: LengthValue | None = None
    after: LengthValue | None = None
    conditions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
