from __future__ import annotations

import hashlib
from pathlib import Path

from specimpact.dirty_excel.evidence_builder import region_evidence_id, region_quote
from specimpact.dirty_excel.models import DirtyRegion
from specimpact.extraction import AliasCatalog, GraphRecords, artifact_for, entity_for
from specimpact.llm_graph.schemas import ExtractedNode, GraphProposal
from specimpact.models import (
    Artifact,
    Entity,
    Evidence,
    EvidenceSupport,
    Relation,
    SourceLocation,
)

ARTIFACT_NODE_TYPES = {
    "Screen": "Screen",
    "ValidationRule": "ValidationRule",
    "API": "API",
    "DBTable": "Table",
    "DBColumn": "Column",
    "ExternalIF": "ExternalIF",
    "BatchJob": "Batch",
    "TestCase": "TestCase",
    "BusinessRule": "Document",
    "DocumentSection": "Document",
}

FIELD_NODE_TYPES = {"ScreenField", "APIField"}
RELATION_MAP = {
    "contains": "DEFINES",
    "displays": "DISPLAYS",
    "accepts_input": "DISPLAYS",
    "validates": "VALIDATES",
    "calls": "CALLS",
    "reads": "READS",
    "writes": "WRITES",
    "maps_to": "REQUEST_FIELD",
    "sends": "SENDS",
    "receives": "RECEIVES",
    "tested_by": "COVERS",
    "depends_on": "CALLS",
    "same_as": "MENTIONS",
    "may_affect": "MENTIONS",
}


def proposals_to_graph(
    proposals: list[GraphProposal],
    regions: dict[str, DirtyRegion],
    chunks_by_region: dict[str, object],
    document,
    aliases: AliasCatalog,
    source_path: Path,
) -> GraphRecords:
    graph = GraphRecords()
    for proposal in proposals:
        if proposal.status == "rejected":
            continue
        region = regions.get(proposal.region_id)
        chunk = chunks_by_region.get(proposal.region_id)
        if not region or not chunk:
            continue
        node_index: dict[str, Artifact | Entity] = {}
        for node in proposal.result.nodes:
            item = _model_for_node(node, document.document_id, aliases)
            if isinstance(item, Artifact):
                graph.artifacts.append(item)
            else:
                graph.entities.append(item)
            node_index[node.temp_id] = item
        for edge in proposal.result.edges:
            source = node_index.get(edge.source_temp_id)
            target = node_index.get(edge.target_temp_id)
            if source is None or target is None:
                continue
            source_id = getattr(source, "artifact_id", getattr(source, "entity_id", ""))
            target_id = getattr(target, "artifact_id", getattr(target, "entity_id", ""))
            relation_type = RELATION_MAP.get(str(edge.relation_type), str(edge.relation_type))
            key = f"{source_id}|{relation_type}|{target_id}|{proposal.region_id}"
            suffix = _short_hash(key)
            relation_id = (
                f"rel.{_slug(source_id)}."
                f"{relation_type.lower()}.{_slug(target_id)}.{suffix}"
            )
            evidence_id = region_evidence_id(proposal.region_id, key)
            relation = Relation(
                relation_id=relation_id,
                relation_type=relation_type,
                source_id=source_id,
                target_id=target_id,
                evidence_ids=[evidence_id],
                extraction_method="llm" if proposal.extraction_method == "llm" else "rule",
                polarity="inferred" if edge.inference_level != "explicit" else "explicit",
                status="unconfirmed",
                match_type="semantic" if edge.inference_level != "explicit" else "exact",
                source_document_ids=[document.document_id],
            )
            evidence = Evidence(
                evidence_id=evidence_id,
                document_id=document.document_id,
                section_id=chunk.section_id,
                chunk_id=chunk.chunk_id,
                quote=region_quote(region),
                evidence_type="dirty_excel_region_relation",
                supports=[
                    EvidenceSupport(
                        type="entity" if isinstance(target, Entity) else "artifact",
                        id=target_id,
                    ),
                    EvidenceSupport(type="relation", id=relation_id),
                ],
                source_location=SourceLocation(
                    file=source_path.as_posix(),
                    line_start=max(1, region.start_row),
                    line_end=max(region.start_row, region.end_row),
                ),
            )
            graph.relations.append(relation)
            graph.evidence.append(evidence)
    return graph


def _model_for_node(
    node: ExtractedNode,
    document_id: str,
    aliases: AliasCatalog,
) -> Artifact | Entity:
    if node.node_type in FIELD_NODE_TYPES:
        item = entity_for(node.display_name, document_id, aliases)
        item.extraction_methods = ["llm"] if "LLM" in node.rationale else ["rule"]
        item.aliases = sorted({*item.aliases, *node.aliases})
        return item
    artifact_type = ARTIFACT_NODE_TYPES.get(node.node_type, "Document")
    item = artifact_for(node.display_name, artifact_type, document_id, aliases)
    item.extraction_methods = ["llm"] if "LLM" in node.rationale else ["rule"]
    item.aliases = sorted({*item.aliases, *node.aliases})
    return item


def _slug(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value)
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or _short_hash(value)


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
