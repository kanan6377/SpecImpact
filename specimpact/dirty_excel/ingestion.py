from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from specimpact.dirty_excel.cell_renderer import write_rendered
from specimpact.dirty_excel.evidence_builder import document_graph_for_regions
from specimpact.dirty_excel.models import (
    DirtyCell,
    DirtyIngestSummary,
    DirtyRegion,
    DirtySheet,
    DirtyWorkbook,
)
from specimpact.dirty_excel.region_detector import detect_regions
from specimpact.dirty_excel.sheet_classifier import classify_sheets
from specimpact.dirty_excel.workbook_reader import (
    preserve_original,
    read_dirty_workbook,
    write_normalized,
)
from specimpact.extraction import AliasCatalog, GraphRecords
from specimpact.graphrag import LLMClient, client_from_config, ensure_llm_consent
from specimpact.llm_graph.extraction import extract_region_heuristic, extract_region_with_llm
from specimpact.llm_graph.graph_merge import proposals_to_graph
from specimpact.llm_graph.schemas import GraphProposal
from specimpact.models import Artifact, Entity, Evidence, Relation
from specimpact.store import LocalStore


def ingest_dirty_excel(
    store: LocalStore,
    path: Path,
    aliases_path: Path | None = None,
    *,
    use_llm: bool = False,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    llm_client: LLMClient | None = None,
) -> DirtyIngestSummary:
    store.init()
    if aliases_path:
        if not aliases_path.is_file():
            raise ValueError(f"Aliases file does not exist: {aliases_path}")
        alias_text = aliases_path.read_text(encoding="utf-8")
        AliasCatalog.parse(alias_text, aliases_path)
        store.write_text(store.root / "aliases.yml", alias_text)
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    workbooks = _workbook_paths(path)
    client = None
    if use_llm:
        client = llm_client or client_from_config(store)
        if client is None:
            raise ValueError(
                "LLM provider not configured; run specimpact llm configure or pass --no-llm"
            )
        ensure_llm_consent(
            client,
            purpose="dirty_excel_region_extraction",
            chunk_count=len(workbooks),
            yes=yes,
            confirm=confirm,
        )
    all_workbooks: list[DirtyWorkbook] = []
    all_sheets: list[DirtySheet] = []
    all_cells: list[DirtyCell] = []
    all_regions: list[DirtyRegion] = []
    all_proposals: list[GraphProposal] = []
    graph = GraphRecords()
    for workbook_path in workbooks:
        workbook, sheets, cells = read_dirty_workbook(workbook_path)
        original = preserve_original(workbook_path, store.root, workbook.workbook_id)
        normalized = write_normalized(store.root, workbook, cells)
        sheets = classify_sheets(sheets, cells, client)
        rendered = write_rendered(store.root, workbook, sheets, cells)
        workbook.original_path = original.as_posix()
        workbook.normalized_path = normalized.as_posix()
        workbook.rendered_paths = [item.as_posix() for item in rendered]
        regions = detect_regions(sheets, cells)
        document_graph, chunks_by_region, document = document_graph_for_regions(
            workbook_path,
            regions,
            source_key=workbook_path.name,
        )
        graph.extend(document_graph)
        proposals = [
            GraphProposal(
                proposal_id=f"proposal_{_short_hash(region.region_id)}",
                region_id=region.region_id,
                extraction_method="llm" if client else "rule",
                result=(
                    extract_region_with_llm(
                        region,
                        [cell for cell in cells if cell.sheet_id == region.sheet_id],
                        client,
                    )
                    if client
                    else extract_region_heuristic(
                        region,
                        [cell for cell in cells if cell.sheet_id == region.sheet_id],
                    )
                ),
            )
            for region in regions
            if region.region_type != "revision_history"
        ]
        graph.extend(
            proposals_to_graph(
                proposals,
                {region.region_id: region for region in regions},
                chunks_by_region,
                document,
                aliases,
                workbook_path,
            )
        )
        all_workbooks.append(workbook)
        all_sheets.extend(sheets)
        all_cells.extend(cells)
        all_regions.extend(regions)
        all_proposals.extend(proposals)
    store.merge_graph(**graph.__dict__)
    _replace_v2_collection(store, "dirty_workbooks", all_workbooks, "workbook_id")
    _replace_v2_collection(store, "dirty_sheets", all_sheets, "sheet_id")
    _replace_v2_collection(store, "dirty_cells", all_cells, "evidence_id")
    _replace_v2_collection(store, "dirty_regions", all_regions, "region_id")
    _replace_v2_collection(store, "graph_proposals", all_proposals, "proposal_id")
    health = inspect_dirty_excel(store)
    store.write_json(store.root / "dirty_excel_health.json", health)
    return DirtyIngestSummary(
        workbooks=len(all_workbooks),
        sheets=len(all_sheets),
        cells=len(all_cells),
        regions=len(all_regions),
        proposals=len(all_proposals),
        artifacts=len(store.read("artifacts", Artifact)),
        entities=len(store.read("entities", Entity)),
        relations=len(store.read("relations", Relation)),
        evidence=len(store.read("evidence", Evidence)),
    )


def inspect_dirty_excel(store_or_path: LocalStore | Path) -> dict[str, object]:
    if isinstance(store_or_path, LocalStore):
        store = store_or_path
        workbooks = store.read("dirty_workbooks", DirtyWorkbook)
        sheets = store.read("dirty_sheets", DirtySheet)
        cells = store.read("dirty_cells", DirtyCell)
        regions = store.read("dirty_regions", DirtyRegion)
        proposals = store.read("graph_proposals", GraphProposal)
        return {
            "workbooks": len(workbooks),
            "sheets": len(sheets),
            "cells": len(cells),
            "regions": len(regions),
            "proposals": len(proposals),
            "unsupported_drawings": sum(
                len(sheet.unsupported_drawings) for sheet in sheets
            ),
            "sheet_types": _counts(sheet.sheet_type for sheet in sheets),
            "region_types": _counts(region.region_type for region in regions),
            "unresolved_mentions": sum(
                len(proposal.result.unresolved_mentions) for proposal in proposals
            ),
            "warnings": sorted(
                {
                    warning
                    for proposal in proposals
                    for warning in proposal.result.warnings
                }
                | {warning for workbook in workbooks for warning in workbook.warnings}
                | {
                    f"Sheet '{sheet.sheet_name}' has unresolved drawing content: "
                    f"{', '.join(sheet.unsupported_drawings)}"
                    for sheet in sheets
                    if sheet.unsupported_drawings
                }
            ),
        }
    workbooks = _workbook_paths(store_or_path)
    summary = {
        "workbooks": len(workbooks),
        "sheets": 0,
        "cells": 0,
        "regions": 0,
        "unsupported_drawings": 0,
        "warnings": [],
    }
    for workbook_path in workbooks:
        workbook, sheets, cells = read_dirty_workbook(workbook_path)
        sheets = classify_sheets(sheets, cells)
        regions = detect_regions(sheets, cells)
        summary["sheets"] += len(sheets)
        summary["cells"] += len(cells)
        summary["regions"] += len(regions)
        summary["unsupported_drawings"] += sum(
            len(sheet.unsupported_drawings) for sheet in sheets
        )
        summary["warnings"].extend(workbook.warnings)
    return summary


def list_graph_proposals(store: LocalStore) -> str:
    return json.dumps(
        [item.model_dump() for item in store.read("graph_proposals", GraphProposal)],
        ensure_ascii=False,
        indent=2,
    )


def decide_graph_proposal(store: LocalStore, proposal_id: str, status: str) -> GraphProposal:
    if status not in {"accepted", "rejected"}:
        raise ValueError("status must be accepted or rejected")
    proposals = store.read("graph_proposals", GraphProposal)
    proposal = next((item for item in proposals if item.proposal_id == proposal_id), None)
    if not proposal:
        raise ValueError(f"Unknown graph proposal: {proposal_id}")
    proposal.status = status  # type: ignore[assignment]
    store.write("graph_proposals", proposals)
    _rebuild_proposal_graph(store, proposal.region_id, proposals)
    return proposal


def _rebuild_proposal_graph(
    store: LocalStore,
    region_id: str,
    proposals: list[GraphProposal],
) -> None:
    all_regions = store.read("dirty_regions", DirtyRegion)
    selected_region = next((item for item in all_regions if item.region_id == region_id), None)
    if not selected_region:
        return
    workbook = next(
        (
            item
            for item in store.read("dirty_workbooks", DirtyWorkbook)
            if item.workbook_id == selected_region.workbook_id
        ),
        None,
    )
    if not workbook:
        return
    source_path = Path(workbook.file_path)
    if not source_path.is_file():
        source_path = Path(workbook.original_path)
    if not source_path.is_file():
        raise ValueError(f"Dirty Excel source is unavailable: {workbook.file_path}")
    regions = [item for item in all_regions if item.workbook_id == workbook.workbook_id]
    region_ids = {item.region_id for item in regions}
    active = [
        item
        for item in proposals
        if item.region_id in region_ids and item.status != "rejected"
    ]
    document_graph, chunks_by_region, document = document_graph_for_regions(
        source_path,
        regions,
        source_key=Path(workbook.file_path).name,
    )
    document_graph.extend(
        proposals_to_graph(
            active,
            {item.region_id: item for item in regions},
            chunks_by_region,
            document,
            AliasCatalog.load(store.root / "aliases.yml"),
            source_path,
        )
    )
    store.merge_graph(**document_graph.__dict__)


def _workbook_paths(path: Path) -> list[Path]:
    if path.is_file() and path.suffix.lower() == ".xlsx":
        return [path]
    if path.is_dir():
        workbooks = sorted(item for item in path.iterdir() if item.suffix.lower() == ".xlsx")
        if workbooks:
            return workbooks
    raise ValueError(f"Excel source contains no .xlsx files: {path}")


def _replace_v2_collection(
    store: LocalStore,
    collection: str,
    incoming: list,
    key: str,
) -> None:
    incoming_ids = {getattr(item, key) for item in incoming}
    model = type(incoming[0]) if incoming else None
    current = store.read(collection, model) if model else []
    kept = [item for item in current if getattr(item, key) not in incoming_ids]
    store.write(collection, kept + incoming)


def _counts(values) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[str(value)] = result.get(str(value), 0) + 1
    return result


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
