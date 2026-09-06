from __future__ import annotations

from pydantic import BaseModel

from specimpact.dirty_excel.models import DirtyCell, DirtySheet, SheetType
from specimpact.graphrag import LLMClient

KEYWORDS: list[tuple[SheetType, tuple[str, ...]]] = [
    ("screen_item_definition", ("画面", "項目名", "入力可否", "screen")),
    ("validation_rule", ("入力チェック", "チェック", "ValidationRule", "必須", "上限")),
    ("api_mapping", ("API", "リクエスト", "レスポンス", "endpoint", "request")),
    ("db_mapping", ("テーブル", "DB", "カラム", "column", "table")),
    ("external_interface", ("外部IF", "IF名", "送信", "受信", "interface")),
    ("test_case", ("試験", "テスト", "期待結果", "境界値", "test")),
    ("glossary", ("用語", "glossary")),
    ("revision_history", ("改訂", "履歴", "revision")),
]

WORKBOOK_FILENAME_HINTS: tuple[tuple[SheetType, tuple[str, ...]], ...] = (
    (
        "external_interface",
        (
            "外部インターフェース",
            "外部インタフェース",
            "外部if",
            "external_if",
            "external interface",
        ),
    ),
    (
        "db_mapping",
        (
            "テーブル定義",
            "ドメイン定義",
            "テーブル・ドメイン",
            "table_definition",
            "domain_definition",
            "table definition",
            "domain definition",
        ),
    ),
    (
        "screen_item_definition",
        (
            "画面・システム機能設計",
            "画面システム機能設計",
            "システム機能設計書(画面)",
            "画面設計",
            "screen_function",
            "screen system function design",
        ),
    ),
    (
        "batch_definition",
        (
            "バッチ・システム機能設計",
            "バッチシステム機能設計",
            "システム機能設計書(バッチ)",
            "batch_function",
            "batch system function design",
        ),
    ),
    (
        "validation_rule",
        ("メッセージ設計", "screen_message", "batch_message", "message design"),
    ),
    ("test_case", ("単体テスト", "単体試験", "unit_test", "unit test")),
)

# A workbook often embeds the same revision block in every sheet.  Header
# signatures therefore take precedence over global keyword counts.
HEADER_SIGNATURES: list[
    tuple[SheetType, tuple[tuple[str, ...], ...]]
] = [
    (
        "external_interface",
        (("外部if", "if名", "interface name"), ("項目名", "物理名", "送信", "受信")),
    ),
    (
        "db_mapping",
        (("テーブル名", "table name", "db定義"), ("カラム名", "column name")),
    ),
    (
        "api_mapping",
        (("api id", "api名", "endpoint"), ("request", "response", "リクエスト", "レスポンス")),
    ),
    (
        "validation_rule",
        (
            ("チェックid", "入力チェック", "validationrule"),
            ("対象項目", "条件", "エラーメッセージ"),
        ),
    ),
    (
        "test_case",
        (("テストケースid", "test case id"), ("期待結果", "expected result")),
    ),
    (
        "screen_item_definition",
        (("画面id", "screen id"), ("項目名", "field name"), ("入力可否", "表示有無")),
    ),
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
    workbook_hint = _workbook_filename_hint(cells)
    for cell in cells:
        if cell.value:
            by_sheet.setdefault(cell.sheet_id, []).append(cell.value)
    result = []
    for sheet in sheets:
        text = " ".join([sheet.sheet_name, *by_sheet.get(sheet.sheet_id, [])[:80]])
        special_type = _special_sheet_type(sheet.sheet_name)
        sheet_type, matches = _classify_text(text)
        header_type, header_matches = _classify_header(text)
        if special_type is not None:
            sheet_type = special_type
            matches = [sheet.sheet_name]
        elif header_matches:
            sheet_type = header_type
            matches = header_matches
        elif workbook_hint is not None:
            sheet_type, hint = workbook_hint
            matches = [hint]
        sheet.sheet_type = sheet_type
        if matches:
            sheet.evidence_level = "layout_and_heading"
            sheet.reason = f"matched keywords: {', '.join(matches[:5])}"
        else:
            sheet.evidence_level = "none"
            sheet.reason = "no sheet-name or heading keyword matched"
        if llm_client is not None and special_type is None:
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


def _workbook_filename_hint(cells: list[DirtyCell]) -> tuple[SheetType, str] | None:
    paths = {cell.file_path for cell in cells if cell.file_path}
    if not paths:
        return None
    filename_text = " ".join(paths).casefold()
    for sheet_type, hints in WORKBOOK_FILENAME_HINTS:
        for hint in hints:
            if hint.casefold() in filename_text:
                return sheet_type, hint
    return None


def _special_sheet_type(name: str) -> SheetType | None:
    folded = name.casefold()
    if any(token in folded for token in ("改訂", "履歴", "revision", "history")):
        return "revision_history"
    if any(
        token in folded
        for token in ("表紙", "目次", "はじめに", "cover", "contents", "toc", "introduction")
    ):
        return "cover"
    return None


def classify_sheet_text(name: str, text: str) -> dict[str, str]:
    sheet_type, matches = _classify_text(f"{name} {text}")
    return {
        "sheet_type": sheet_type,
        "evidence_level": "layout_and_heading" if matches else "none",
        "reason": f"matched keywords: {', '.join(matches[:5])}" if matches else "no match",
    }


def _classify_text(text: str) -> tuple[SheetType, list[str]]:
    header_type, header_matches = _classify_header(text)
    if header_matches:
        return header_type, header_matches

    return _classify_keywords(text)


def _classify_header(text: str) -> tuple[SheetType, list[str]]:
    folded = text.casefold()
    for sheet_type, signature in HEADER_SIGNATURES:
        matches = [
            next(token for token in group if token.casefold() in folded)
            for group in signature
            if any(token.casefold() in folded for token in group)
        ]
        if len(matches) == len(signature):
            return sheet_type, matches
    return "unknown", []


def _classify_keywords(text: str) -> tuple[SheetType, list[str]]:
    folded = text.casefold()
    best_type: SheetType = "unknown"
    best_matches: list[str] = []
    for sheet_type, keywords in KEYWORDS:
        matches = [keyword for keyword in keywords if keyword.casefold() in folded]
        if len(matches) > len(best_matches):
            best_type = sheet_type
            best_matches = matches
    return best_type, best_matches
