from __future__ import annotations

import pytest

from specimpact.dirty_excel.models import DirtyCell, DirtySheet
from specimpact.dirty_excel.region_detector import detect_regions
from specimpact.dirty_excel.sheet_classifier import classify_sheets


def _sheet(name: str) -> DirtySheet:
    return DirtySheet(
        workbook_id="wb-1",
        sheet_id="sheet-1",
        sheet_name=name,
        sheet_index=0,
    )


def _cells(path: str, values: list[str], sheet_name: str = "データ") -> list[DirtyCell]:
    return [
        DirtyCell(
            workbook_id="wb-1",
            file_path=path,
            sheet_id="sheet-1",
            sheet_name=sheet_name,
            cell=f"{chr(65 + index)}1",
            evidence_id=f"ev-{index}",
            value=value,
            data_type="s",
            row=1,
            column=index + 1,
        )
        for index, value in enumerate(values)
    ]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("外部インターフェース設計書.xlsx", "external_interface"),
        ("テーブル・ドメイン定義書.xlsx", "db_mapping"),
        ("画面・システム機能設計書.xlsx", "screen_item_definition"),
        ("バッチ・システム機能設計書.xlsx", "batch_definition"),
        ("メッセージ設計書.xlsx", "validation_rule"),
        ("単体テスト仕様書.xlsx", "test_case"),
        ("03_screen_function_WA10201.xlsx", "screen_item_definition"),
        ("07_batch_function_BA10601.xlsx", "batch_definition"),
        ("10_external_if_N21AA001.xlsx", "external_interface"),
        ("13_screen_message_spec.xlsx", "validation_rule"),
        ("19_batch_unit_test_BA10601.xlsx", "test_case"),
    ],
)
def test_filename_hints_classify_generic_sheets(filename: str, expected: str) -> None:
    sheets = classify_sheets([_sheet("データ")], _cells(filename, ["ID", "名称"]))

    assert sheets[0].sheet_type == expected
    assert "matched keywords" in sheets[0].reason


def test_cover_index_and_revision_do_not_inherit_workbook_type() -> None:
    sheets = [_sheet(name) for name in ("表紙", "目次", "はじめに", "改訂履歴", "機能一覧")]
    for index, sheet in enumerate(sheets):
        sheet.sheet_id = f"sheet-{index}"
    cells = [
        *_cells("画面・システム機能設計書.xlsx", ["設計書", "会社名"], "表紙"),
        *_cells("画面・システム機能設計書.xlsx", ["画面一覧"], "目次"),
        *_cells("画面・システム機能設計書.xlsx", ["利用方法"], "はじめに"),
        *_cells("画面・システム機能設計書.xlsx", ["改訂日", "改訂内容"], "改訂履歴"),
        *_cells("画面・システム機能設計書.xlsx", ["画面ID", "項目名"], "機能一覧"),
    ]
    offsets = ((0, 2, 0), (2, 3, 1), (3, 4, 2), (4, 6, 3), (6, 8, 4))
    for start, end, index in offsets:
        for cell in cells[start:end]:
            cell.sheet_id = f"sheet-{index}"

    classified = classify_sheets(sheets, cells)

    assert [sheet.sheet_type for sheet in classified] == [
        "cover",
        "cover",
        "cover",
        "revision_history",
        "screen_item_definition",
    ]


def test_explicit_table_headers_override_workbook_filename_hint() -> None:
    sheets = classify_sheets(
        [_sheet("データ定義")],
        _cells("10_external_if_N21AA001.xlsx", ["テーブル名", "カラム名"]),
    )

    assert sheets[0].sheet_type == "db_mapping"


@pytest.mark.parametrize(
    ("sheet_type", "headers", "region_type"),
    [
        ("db_mapping", ["論理名称", "物理名称", "桁数"], "db_mapping_table"),
        ("external_interface", ["項目名", "項目ID", "長さ(Byte)"], "external_if_table"),
        ("test_case", ["入力条件", "期待結果"], "test_case_table"),
    ],
)
def test_compound_japanese_headers_are_recognized(
    sheet_type: str, headers: list[str], region_type: str
) -> None:
    sheet = _sheet("データ")
    sheet.sheet_type = sheet_type
    cells = _cells("設計書.xlsx", headers)

    regions = detect_regions([sheet], cells)

    assert [region.region_type for region in regions] == [region_type]
