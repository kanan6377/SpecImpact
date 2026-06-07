from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

NodeType = Literal[
    "Screen",
    "ScreenField",
    "ValidationRule",
    "API",
    "APIField",
    "DBTable",
    "DBColumn",
    "ExternalIF",
    "BatchJob",
    "TestCase",
    "BusinessRule",
    "DocumentSection",
]

RelationType = Literal[
    "contains",
    "displays",
    "accepts_input",
    "validates",
    "calls",
    "reads",
    "writes",
    "maps_to",
    "sends",
    "receives",
    "tested_by",
    "depends_on",
    "same_as",
    "may_affect",
    "REQUEST_FIELD",
    "RESPONSE_FIELD",
    "DEFINES",
    "READS",
    "WRITES",
    "DISPLAYS",
    "VALIDATES",
    "SENDS",
    "RECEIVES",
    "CALLS",
    "COVERS",
]

InferenceLevel = Literal[
    "explicit",
    "layout_inferred",
    "semantic_inferred",
    "cross_reference_inferred",
]


class ExtractedNode(BaseModel):
    temp_id: str
    node_type: NodeType
    display_name: str
    canonical_hint: str | None = None
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, str] = Field(default_factory=dict)
    evidence_ids: list[str]
    rationale: str


class ExtractedEdge(BaseModel):
    temp_id: str
    source_temp_id: str
    relation_type: RelationType
    target_temp_id: str
    evidence_ids: list[str]
    inference_level: InferenceLevel
    rationale: str


class RegionExtractionResult(BaseModel):
    region_id: str
    nodes: list[ExtractedNode]
    edges: list[ExtractedEdge]
    unresolved_mentions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class GraphProposal(BaseModel):
    proposal_id: str
    region_id: str
    extraction_method: str = "rule"
    status: Literal["pending", "accepted", "rejected"] = "pending"
    result: RegionExtractionResult


class AliasCandidate(BaseModel):
    candidate_id: str
    target_id: str
    aliases: list[str]
    judgement: Literal["same", "related", "different", "unsure"] = "unsure"
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    status: Literal["pending", "confirmed", "rejected"] = "pending"
    compared_entity_ids: list[str] = Field(default_factory=list)
    surrounding_node_ids: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)
    llm_reason: str = ""


class AliasJudgement(BaseModel):
    judgement: Literal["same", "related", "different", "unsure"] = "unsure"
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class ImpactHypothesisLLMResult(BaseModel):
    impact_type: str = "review"
    required_actions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    uncertainty: str = "medium"
    reason: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
