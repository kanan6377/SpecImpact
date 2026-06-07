from __future__ import annotations

from pydantic import BaseModel

from specimpact.dirty_excel.models import DirtyCell, DirtySheet, SheetType
from specimpact.graphrag import LLMClient

KEYWORDS: list[tuple[SheetType, tuple[str, ...]]] = [
    ("revision_history", ("改訂", "履歴", "revision")),
    ("screen_item_definition", ("画面", "項目名", "入力可否", "screen")),
    ("validation_rule", ("入力チェック", "チェック", "ValidationRule", "必須", "上限")),
    ("api_mapping", ("API", "リクエスト", "レスポンス", "endpoint", "request")),
    ("db_mapping", ("テーブル", "DB", "カラム", "column", "table")),
    ("external_interface", ("外部IF", "IF名", "送信", "受信", "interface")),
    ("test_case", ("試験", "テスト", "期待結果", "境界値", "test")),
    ("glossary", ("用語", "glossary")),
]


class SheetClassificationResult(BaseModel):
    sheet_type: SheetType = "unknown"
    reason: str = ""
    evidence_level: str = "llm_sample"


def classify_sheets(
    sheets: list[DirtySheet],
    cells: list[DirtyCell],
    llm_client: LLMClient | None = None,
) -> list[DirtySheet]:
    by_sheet = {sheet.sheet_id: [] for sheet in sheets}
    for cell in cells:
        if cell.value:
            by_sheet.setdefault(cell.sheet_id, []).append(cell.value)
    result = []
    for sheet in sheets:
        text = " ".join([sheet.sheet_name, *by_sheet.get(sheet.sheet_id, [])[:80]])
        sheet_type, matches = _classify_text(text)
        sheet.sheet_type = sheet_type
        if matches:
            sheet.evidence_level = "layout_and_heading"
            sheet.reason = f"matched keywords: {', '.join(matches[:5])}"
        else:
            sheet.evidence_level = "none"
            sheet.reason = "no sheet-name or heading keyword matched"
        if llm_client is not None:
            sample = "\n".join(by_sheet.get(sheet.sheet_id, [])[:120])
            llm_result = llm_client.structured(
                "dirty_excel_sheet_classification",
                {
                    "sheet_name": sheet.sheet_name,
                    "heuristic_sheet_type": sheet.sheet_type,
                    "max_row": sheet.max_row,
                    "max_column": sheet.max_column,
                    "cell_sample": sample,
                    "instruction": (
                        "Classify the SIer design workbook sheet. Prefer explicit table "
                        "headings over sheet name alone."
                    ),
                },
                SheetClassificationResult,
            )
            if llm_result.sheet_type != "unknown":
                sheet.sheet_type = llm_result.sheet_type
                sheet.evidence_level = llm_result.evidence_level or "llm_sample"
                sheet.reason = f"LLM classification: {llm_result.reason}"
        result.append(sheet)
    return result


def classify_sheet_text(name: str, text: str) -> dict[str, str]:
    sheet_type, matches = _classify_text(f"{name} {text}")
    return {
        "sheet_type": sheet_type,
        "evidence_level": "layout_and_heading" if matches else "none",
        "reason": f"matched keywords: {', '.join(matches[:5])}" if matches else "no match",
    }


def _classify_text(text: str) -> tuple[SheetType, list[str]]:
    best_type: SheetType = "unknown"
    best_matches: list[str] = []
    folded = text.casefold()
    for sheet_type, keywords in KEYWORDS:
        matches = [keyword for keyword in keywords if keyword.casefold() in folded]
        if len(matches) > len(best_matches):
            best_type = sheet_type
            best_matches = matches
    return best_type, best_matches
