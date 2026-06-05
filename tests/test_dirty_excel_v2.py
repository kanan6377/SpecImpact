from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Font, PatternFill

from specimpact.dirty_excel.ingestion import ingest_dirty_excel
from specimpact.dirty_excel.region_detector import detect_regions
from specimpact.dirty_excel.sheet_classifier import classify_sheets
from specimpact.dirty_excel.workbook_reader import read_dirty_workbook
from specimpact.graphrag import FakeLLMClient
from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.decision_store import set_impact_status
from specimpact.impact_management.review_session import analyze_change_llm_first
from specimpact.llm_graph.entity_resolution import (
    decide_alias_candidate,
    suggest_alias_candidates,
)
from specimpact.llm_graph.extraction import extract_region_with_llm
from specimpact.llm_graph.schemas import AliasCandidate
from specimpact.models import Entity
from specimpact.store import LocalStore
from specimpact.webui.registry import ProjectRegistry
from specimpact.webui.services import dirty_excel_data, execute, impact_decisions_data

ROOT = Path(__file__).parents[1]
SIER = ROOT / "examples" / "japanese_sier_excel"


def test_dirty_workbook_normalization_preserves_cells_and_regions(tmp_path: Path) -> None:
    workbook_path = tmp_path / "dirty.xlsx"
    _write_dirty_workbook(workbook_path)
    store = LocalStore(tmp_path / ".specimpact")

    summary = ingest_dirty_excel(store, workbook_path)

    assert summary.workbooks == 1
    assert summary.cells >= 10
    assert summary.regions >= 2
    assert (store.root / "sources" / "original").is_dir()
    normalized = next((store.root / "sources" / "normalized").glob("*.jsonl"))
    assert normalized.is_file()

    _workbook, sheets, cells = read_dirty_workbook(workbook_path)
    assert any(cell.merged_range == "A1:B1" for cell in cells)
    assert any(cell.style.font_bold for cell in cells)
    assert any(cell.style.fill_color for cell in cells)
    assert any(cell.comment == "owner note" for cell in cells)
    assert any(cell.hyperlink == "https://example.com/spec" for cell in cells)
    assert any(cell.is_hidden_row for cell in cells)
    assert any(cell.is_hidden_col for cell in cells)

    regions = detect_regions(classify_sheets(sheets, cells), cells)
    region_types = {region.region_type for region in regions}
    assert {"revision_history", "screen_item_table", "validation_block"} <= region_types


def test_region_llm_extraction_keeps_only_valid_evidence(tmp_path: Path) -> None:
    workbook_path = tmp_path / "dirty.xlsx"
    _write_dirty_workbook(workbook_path)
    _workbook, sheets, cells = read_dirty_workbook(workbook_path)
    sheets = classify_sheets(sheets, cells)
    region = next(
        region
        for region in detect_regions(sheets, cells)
        if region.region_type == "screen_item_table"
    )
    evidence_id = region.evidence_ids[0]
    valid = {
        "region_id": region.region_id,
        "nodes": [
            {
                "temp_id": "screen",
                "node_type": "Screen",
                "display_name": "入会申込画面",
                "canonical_hint": None,
                "aliases": [],
                "properties": {},
                "evidence_ids": [evidence_id],
                "rationale": "LLM extracted from heading",
            },
            {
                "temp_id": "field",
                "node_type": "ScreenField",
                "display_name": "利用限度額",
                "canonical_hint": None,
                "aliases": [],
                "properties": {},
                "evidence_ids": [evidence_id],
                "rationale": "LLM extracted from row",
            },
        ],
        "edges": [
            {
                "temp_id": "edge",
                "source_temp_id": "screen",
                "relation_type": "DISPLAYS",
                "target_temp_id": "field",
                "evidence_ids": [evidence_id],
                "inference_level": "explicit",
                "rationale": "explicit row",
            }
        ],
        "unresolved_mentions": [],
        "warnings": [],
    }
    invalid = {
        **valid,
        "nodes": [{**valid["nodes"][0], "evidence_ids": ["missing"]}],
        "edges": [],
    }

    result = extract_region_with_llm(
        region,
        cells,
        FakeLLMClient({"dirty_excel_region_extraction": [valid, invalid]}),
    )
    assert len(result.nodes) == 2
    assert len(result.edges) == 1
    cleaned = extract_region_with_llm(
        region,
        cells,
        FakeLLMClient({"dirty_excel_region_extraction": invalid}),
    )
    assert cleaned.nodes == []


def test_alias_inference_confirm_and_reject_persist(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    store.write(
        "entities",
        [
            Entity(
                entity_id="entity.credit_limit.jp",
                entity_type="BusinessField",
                display_name="利用限度額",
                canonical_name="credit_limit_jp",
            ),
            Entity(
                entity_id="entity.credit_limit.api",
                entity_type="BusinessField",
                display_name="requestedCreditLimit",
                canonical_name="requested_credit_limit",
            ),
            Entity(
                entity_id="entity.credit_limit.db",
                entity_type="BusinessField",
                display_name="REQUESTED_CREDIT_LIMIT",
                canonical_name="requested_credit_limit",
            ),
        ],
    )

    assert suggest_alias_candidates(store, use_llm=True) == 1
    candidate = store.read("alias_candidates", AliasCandidate)[0]
    decide_alias_candidate(store, candidate.candidate_id, "confirmed")
    aliases = (store.root / "aliases.yml").read_text(encoding="utf-8")
    assert "requestedCreditLimit" in aliases
    decide_alias_candidate(store, candidate.candidate_id, "rejected")
    assert store.read("alias_candidates", AliasCandidate)[0].status == "rejected"


def test_llm_first_impact_from_dirty_excel_credit_limit(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_dirty_excel(store, SIER / "docs", SIER / "aliases.yml")
    parse_change_atoms(store, SIER / "changes" / "利用限度額_上限変更.md")

    report = analyze_change_llm_first(store, SIER / "changes" / "利用限度額_上限変更.md")

    must_ids = {
        item.artifact_id
        for item in report.impacts
        if item.review_priority == "must_review"
    }
    assert {
        "screen.enrollment_application",
        "api.enrollment_application",
        "column.requested_credit_limit",
        "validation.credit_limit_upper_bound",
        "external_if.credit_screening",
        "test.credit_limit_boundary",
    } <= must_ids


def test_gui_dirty_excel_and_impact_decision_services(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = ProjectRegistry(tmp_path / "registry").add(workspace)
    execute(project, "init", {})
    execute(
        project,
        "ingest_dirty_excel",
        {"path": str(SIER / "docs"), "aliases": str(SIER / "aliases.yml")},
    )
    dirty = dirty_excel_data(project)
    assert dirty["summary"]["regions"] >= 6

    result = execute(
        project,
        "analyze_llm_first",
        {"path": str(SIER / "changes" / "利用限度額_上限変更.md")},
    )
    assert result["result"]["candidates"] >= 6
    decision = set_impact_status(
        LocalStore(workspace / ".specimpact"),
        "impact.change.利用限度額_上限変更.api.enrollment_application",
        "accepted",
        "reviewed",
    )
    assert decision.status == "accepted"
    assert impact_decisions_data(project)


def _write_dirty_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "画面項目定義"
    sheet.merge_cells("A1:B1")
    sheet["A1"] = "改訂履歴"
    sheet["A1"].font = Font(bold=True)
    sheet["A1"].fill = PatternFill("solid", fgColor="FFFFCC")
    sheet["A1"].comment = Comment("owner note", "qa")
    sheet["A1"].hyperlink = "https://example.com/spec"
    sheet["A2"] = "1.0"
    sheet["B2"] = "初版"
    sheet.row_dimensions[2].hidden = True
    sheet.column_dimensions["F"].hidden = True
    sheet.append([])
    sheet.append(["画面ID", "画面名", "項目ID", "項目名", "物理名", "入力可否"])
    sheet.append(["SCR-001", "入会申込画面", "F-001", "利用限度額", "requestedCreditLimit", "可"])
    sheet.append([])
    sheet.append(["チェックID", "チェック名", "対象項目", "物理名", "上限"])
    sheet.append(
        ["CHK-001", "利用限度額入力チェック", "利用限度額", "requestedCreditLimit", "999万円"]
    )
    workbook.save(path)
