from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from specimpact.dirty_excel.models import DirtyCell, DirtyRegion, DirtySheet
from specimpact.extraction import AliasCatalog, GraphRecords, artifact_for, entity_for
from specimpact.llm_graph.schemas import GraphProposal
from specimpact.models import Evidence, EvidenceSupport, Relation, SourceLocation

SHEET_ARTIFACT_TYPES = {
    "screen_layout": "Screen",
    "screen_item_definition": "Screen",
    "event_definition": "Screen",
    "validation_rule": "ValidationRule",
    "api_mapping": "API",
    "db_mapping": "Table",
    "external_interface": "ExternalIF",
    "batch_definition": "Batch",
    "test_case": "TestCase",
    "glossary": "Document",
    "unknown": "Document",
}

SHEET_RELATION_TYPES = {
    "screen_layout": "DISPLAYS",
    "screen_item_definition": "DISPLAYS",
    "event_definition": "DISPLAYS",
    "validation_rule": "VALIDATES",
    "api_mapping": "REQUEST_FIELD",
    "db_mapping": "DEFINES",
    "external_interface": "SENDS",
    "batch_definition": "READS",
    "test_case": "COVERS",
    "glossary": "DEFINES",
    "unknown": "MENTIONS",
}

FIELD_NODE_TYPES = {"ScreenField", "APIField"}
GENERIC_TERMS = {
    "no",
    "id",
    "項目",
    "項目名",
    "物理名",
    "物理名称",
    "論理名",
    "論理名称",
    "ドメイン名",
    "備考",
    "必須",
    "桁数",
    "入力値",
    "期待結果",
}


def build_sheet_mention_graph(
    source_path: Path,
    sheets: list[DirtySheet],
    cells: list[DirtyCell],
    regions: list[DirtyRegion],
    proposals: list[GraphProposal],
    chunks_by_region: dict[str, object],
    document,
    aliases: AliasCatalog,
) -> GraphRecords:
    """Build a cheap, evidence-backed sheet index before LLM refinement.

    Dirty workbooks frequently use layouts that are too irregular for row extraction, while
    still naming the changed business field in a concrete cell. This index keeps that exact
    evidence connected to the containing design sheet. Typed LLM proposals can later refine the
    conservative sheet-level relation without being required for baseline recall.
    """

    candidates = _entity_candidates(proposals, aliases, document.document_id)
    if not candidates:
        return GraphRecords()

    cells_by_sheet: dict[str, list[DirtyCell]] = defaultdict(list)
    for cell in cells:
        cells_by_sheet[cell.sheet_id].append(cell)
    sheets_by_id = {sheet.sheet_id: sheet for sheet in sheets}

    graph = GraphRecords()
    seen_artifacts: set[str] = set()
    seen_entities: set[str] = set()
    for region in regions:
        sheet = sheets_by_id.get(region.sheet_id)
        chunk = chunks_by_region.get(region.region_id)
        if (
            sheet is None
            or chunk is None
            or sheet.sheet_type in {"cover", "revision_history"}
            or region.region_type == "revision_history"
            or _non_design_sheet(sheet.sheet_name)
        ):
            continue
        region_cells = [
            cell
            for cell in cells_by_sheet.get(region.sheet_id, [])
            if region.start_row <= cell.row <= region.end_row
            and region.start_column <= cell.column <= region.end_column
        ]
        if not region_cells:
            continue
        artifact_type = SHEET_ARTIFACT_TYPES.get(sheet.sheet_type, "Document")
        relation_type = SHEET_RELATION_TYPES.get(sheet.sheet_type, "MENTIONS")
        artifact = artifact_for(
            _sheet_display_name(source_path, sheet),
            artifact_type,
            document.document_id,
            aliases,
        )
        for entity_id, candidate in candidates.items():
            matching = _matching_cells(region_cells, candidate["terms"])
            if not matching:
                continue
            entity = candidate["entity"]
            key = f"{artifact.artifact_id}|{relation_type}|{entity_id}|{region.region_id}"
            suffix = _short_hash(key)
            relation_id = (
                f"rel.{_slug(artifact.artifact_id)}.{relation_type.lower()}."
                f"{_slug(entity_id)}.{suffix}"
            )
            matching_rows = _matching_rows(matching)
            evidence_ids = [
                f"ev.{_short_hash(f'{key}|row:{row}')}" for row in matching_rows
            ]
            if artifact.artifact_id not in seen_artifacts:
                graph.artifacts.append(artifact)
                seen_artifacts.add(artifact.artifact_id)
            if entity_id not in seen_entities:
                graph.entities.append(entity)
                seen_entities.add(entity_id)
            graph.relations.append(
                Relation(
                    relation_id=relation_id,
                    relation_type=relation_type,
                    source_id=artifact.artifact_id,
                    target_id=entity_id,
                    evidence_ids=evidence_ids,
                    extraction_method="rule",
                    polarity="explicit",
                    status="unconfirmed",
                    match_type="exact",
                    source_document_ids=[document.document_id],
                )
            )
            for row, evidence_id in zip(matching_rows, evidence_ids, strict=True):
                row_matches = [cell for cell in matching if cell.row == row]
                graph.evidence.append(
                    Evidence(
                        evidence_id=evidence_id,
                        document_id=document.document_id,
                        section_id=chunk.section_id,
                        chunk_id=chunk.chunk_id,
                        quote=_mention_quote(
                            source_path,
                            sheet,
                            region,
                            region_cells,
                            row_matches,
                        ),
                        evidence_type="dirty_excel_cell_mention",
                        supports=[
                            EvidenceSupport(type="entity", id=entity_id),
                            EvidenceSupport(type="relation", id=relation_id),
                        ],
                        source_location=SourceLocation(
                            file=source_path.as_posix(),
                            line_start=row,
                            line_end=row,
                        ),
                    )
                )
                if evidence_id not in region.evidence_ids:
                    region.evidence_ids.append(evidence_id)
    return graph


def _entity_candidates(
    proposals: list[GraphProposal],
    aliases: AliasCatalog,
    document_id: str,
) -> dict[str, dict[str, object]]:
    manual_values: list[tuple[str, list[str]]] = []
    for item_id, details in aliases.entries.items():
        if not isinstance(details, dict) or details.get("canonical_type") != "BusinessField":
            continue
        terms = aliases.aliases_for(item_id)
        if terms:
            manual_values.append((terms[0], terms))
    values = list(manual_values)
    if not values:
        for proposal in proposals:
            for node in proposal.result.nodes:
                if node.node_type in FIELD_NODE_TYPES:
                    values.append((node.display_name, [node.display_name, *node.aliases]))

    candidates: dict[str, dict[str, object]] = {}
    for display_name, raw_terms in values:
        entity = entity_for(display_name, document_id, aliases)
        row = candidates.setdefault(entity.entity_id, {"entity": entity, "terms": set()})
        terms = row["terms"]
        assert isinstance(terms, set)
        for term in raw_terms:
            clean = term.strip()
            if _useful_term(clean):
                terms.add(clean)
        current_entity = row["entity"]
        current_entity.aliases = sorted({*current_entity.aliases, *terms})
    return {
        entity_id: row
        for entity_id, row in candidates.items()
        if isinstance(row["terms"], set) and row["terms"]
    }


def _matching_cells(cells: list[DirtyCell], terms: object) -> list[DirtyCell]:
    if not isinstance(terms, set):
        return []
    normalized_terms = [_normalize(term) for term in terms if isinstance(term, str)]
    return [
        cell
        for cell in cells
        if cell.value
        and not (cell.cell == "A1" and _normalize(cell.value) in {"pj名", "プロジェクト名"})
        and any(_contains(_normalize(cell.value), term) for term in normalized_terms if term)
    ]


def _matching_rows(cells: list[DirtyCell]) -> list[int]:
    return sorted({cell.row for cell in cells})


def _contains(value: str, term: str) -> bool:
    if re.fullmatch(r"[a-z0-9_]+", term):
        return bool(re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", value))
    return term in value


def _mention_quote(
    source_path: Path,
    sheet: DirtySheet,
    region: DirtyRegion,
    region_cells: list[DirtyCell],
    matching: list[DirtyCell],
) -> str:
    match_rows = sorted({cell.row for cell in matching})
    selected_rows = {row + offset for row in match_rows for offset in (-1, 0, 1)}
    selected = [
        cell for cell in region_cells if cell.row in selected_rows and cell.value not in (None, "")
    ]
    selected.sort(key=lambda item: (item.row, item.column))
    cells_text = " / ".join(f"[{cell.cell}] {cell.value}" for cell in selected)
    prefix = f"[{source_path.name} / {sheet.sheet_name}!{region.range}] "
    return (prefix + cells_text)[:4000]


def _sheet_display_name(source_path: Path, sheet: DirtySheet) -> str:
    workbook = re.sub(r"^\d+_", "", source_path.stem)
    return f"{workbook} / {sheet.sheet_name}"


def _non_design_sheet(name: str) -> bool:
    folded = _normalize(name).replace(" ", "")
    return any(
        token in folded
        for token in ("表紙", "目次", "変更履歴", "改訂履歴", "revisionhistory", "はじめに")
    )


def _useful_term(term: str) -> bool:
    normalized = _normalize(term)
    return len(normalized) >= 2 and normalized not in GENERIC_TERMS


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _slug(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "_" for char in value)
    return "_".join(part for part in normalized.split("_") if part) or _short_hash(value)


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
