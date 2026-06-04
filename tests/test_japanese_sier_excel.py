from __future__ import annotations

from pathlib import Path

from specimpact.core import analyze_change
from specimpact.models import Evidence
from specimpact.reports import export_report_excel
from specimpact.store import LocalStore
from specimpact.tabular_loaders import ingest_excel, inspect_excel_folder

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "japanese_sier_excel"


def test_japanese_sier_excel_mvp_flow(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    records = ingest_excel(store, SAMPLE / "docs", SAMPLE / "aliases.yml")
    health = inspect_excel_folder(SAMPLE / "docs")
    assert len(records) == 6
    assert health["workbooks"] == 6
    assert health["sheets"] == 6

    report = analyze_change(
        store,
        next((SAMPLE / "changes").glob("*.md")),
        no_llm=True,
    )
    grouped = report.grouped()
    must_ids = {item["artifact_id"] for item in grouped["must_review"]}
    assert {
        "screen.enrollment_application",
        "api.enrollment_application",
        "column.requested_credit_limit",
        "validation.credit_limit_upper_bound",
        "external_if.credit_screening",
        "test.credit_limit_boundary",
    } <= must_ids
    assert "screen.item_7bcfde24d4" not in must_ids

    evidence = store.read("evidence", Evidence)
    assert any("!" in item.quote and item.source_location.line_start >= 2 for item in evidence)
    assert export_report_excel(store).is_file()
