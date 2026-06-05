from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SheetType = Literal[
    "revision_history",
    "cover",
    "screen_layout",
    "screen_item_definition",
    "event_definition",
    "validation_rule",
    "api_mapping",
    "db_mapping",
    "external_interface",
    "batch_definition",
    "test_case",
    "glossary",
    "unknown",
]

RegionType = Literal[
    "revision_history",
    "screen_item_table",
    "validation_block",
    "api_mapping_table",
    "db_mapping_table",
    "external_if_table",
    "test_case_table",
    "glossary_table",
    "note_block",
    "unknown",
]


class CellStyle(BaseModel):
    fill_color: str | None = None
    font_bold: bool = False
    border: bool = False
    number_format: str | None = None
    horizontal: str | None = None
    vertical: str | None = None


class DirtyCell(BaseModel):
    workbook_id: str
    file_path: str
    sheet_id: str
    sheet_name: str
    cell: str
    evidence_id: str
    value: str | None = None
    data_type: str
    row: int
    column: int
    merged_range: str | None = None
    style: CellStyle = Field(default_factory=CellStyle)
    hyperlink: str | None = None
    comment: str | None = None
    is_hidden_row: bool = False
    is_hidden_col: bool = False


class DirtySheet(BaseModel):
    workbook_id: str
    sheet_id: str
    sheet_name: str
    sheet_index: int
    sheet_type: SheetType = "unknown"
    evidence_level: str = "none"
    reason: str = ""
    max_row: int = 0
    max_column: int = 0
    hidden: bool = False


class DirtyWorkbook(BaseModel):
    workbook_id: str
    file_path: str
    original_path: str
    normalized_path: str
    rendered_paths: list[str] = Field(default_factory=list)
    sheet_ids: list[str] = Field(default_factory=list)


class DirtyRegion(BaseModel):
    region_id: str
    workbook_id: str
    sheet_id: str
    sheet_name: str
    range: str
    region_type: RegionType = "unknown"
    rendered_text: str
    evidence_ids: list[str]
    start_row: int
    end_row: int
    start_column: int
    end_column: int


class DirtyIngestSummary(BaseModel):
    workbooks: int = 0
    sheets: int = 0
    cells: int = 0
    regions: int = 0
    proposals: int = 0
    artifacts: int = 0
    entities: int = 0
    relations: int = 0
    evidence: int = 0
