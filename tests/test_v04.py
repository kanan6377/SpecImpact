from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.store import LocalStore
from specimpact.tabular_loaders import ingest_csv, ingest_excel

ROOT = Path(__file__).parents[1]
STRUCTURED = ROOT / "examples" / "credit_card_enrollment" / "structured"
runner = CliRunner()


def make_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "fields"
    sheet.append(["field_name", "display_name", "type"])
    sheet.append(["requested_credit_limit", "希望利用限度額", "INTEGER"])
    workbook.save(path)


def test_csv_loader(tmp_path: Path) -> None:
    records = ingest_csv(
        LocalStore(tmp_path / ".specimpact"), STRUCTURED / "card_application_fields.csv"
    )
    assert records[0]["headers"] == ["field_name", "display_name", "type"]
    assert records[0]["rows"][1]["field_name"] == "requested_credit_limit"


def test_excel_loader(tmp_path: Path) -> None:
    path = tmp_path / "fields.xlsx"
    make_workbook(path)
    records = ingest_excel(LocalStore(tmp_path / ".specimpact"), path)
    assert records[0]["display_name"] == "fields"
    assert records[0]["rows"][0]["field_name"] == "requested_credit_limit"


def test_v04_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "fields.xlsx"
    make_workbook(path)
    csv_result = runner.invoke(app, ["ingest-csv", str(STRUCTURED / "card_application_fields.csv")])
    excel_result = runner.invoke(app, ["ingest-excel", str(path)])
    assert csv_result.exit_code == 0
    assert excel_result.exit_code == 0
