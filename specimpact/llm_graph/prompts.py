DIRTY_EXCEL_REGION_EXTRACTION_PROMPT = """
You are a SpecImpact extraction backend for SIer Excel design documents.
Return JSON only. Extract design nodes and relations from one cell-addressed region.
Every node and edge must cite evidence_ids from the supplied payload.
Do not treat revision history as business design content.
Use semantic_inferred only when the relation is inferred rather than explicit.
Put "同上", "上記と同じ", and "別紙参照" style references into unresolved_mentions.
"""


REGION_TYPE_INSTRUCTIONS = {
    "screen_item_table": """
Extract Screen, ScreenField, API, and ValidationRule references.
Merged parent headers usually name the screen or section. Item name, physical name, required flag,
length, input constraint, and notes are properties of the field. If a row says 呼び出すAPI,
create Screen CALLS API. If validation text is present, create ValidationRule VALIDATES field.
""",
    "validation_block": """
Extract ValidationRule and the target ScreenField/APIField/BusinessRule. Upper/lower bounds,
required checks, digit length, and error messages are properties. If a before value such as
999万円 appears, preserve it in properties. Treat 同上 as unresolved unless the referenced row is
unambiguous in the same region.
""",
    "api_mapping_table": """
Extract API and APIField. Request/response direction controls REQUEST_FIELD or RESPONSE_FIELD.
Japanese logical names and camelCase physical names may be aliases for the same business field,
but do not emit same_as unless the evidence directly connects them in the row.
""",
    "db_mapping_table": """
Extract DBTable and DBColumn. Physical column names such as REQUESTED_CREDIT_LIMIT should be
DBColumn nodes. Logical names can become ScreenField or BusinessField nodes when explicitly
mapped. Create DBTable contains DBColumn and DBColumn DEFINES field relations.
""",
    "external_if_table": """
Extract ExternalIF and APIField/BusinessField items. Direction or column headings determine
SENDS/RECEIVES. Keep partner system names as ExternalIF nodes. 別紙参照 must go to
unresolved_mentions unless the target is present in the region.
""",
    "test_case_table": """
Extract TestCase nodes and COVERS relations to fields, validation rules, APIs, or DB columns.
Boundary values such as 9999万円 and 10000万円 are important properties and evidence.
""",
}


DIRTY_EXCEL_FEW_SHOTS = [
    {
        "input_hint": "画面項目 row: 項目名=利用限度額, 物理名=requestedCreditLimit, 必須=Y",
        "expected": "Screen DISPLAYS ScreenField with aliases/properties and row evidence.",
    },
    {
        "input_hint": "チェック row: 対象項目=利用限度額, 上限=999万円, 備考=同上",
        "expected": "ValidationRule VALIDATES field; unresolved_mentions includes 同上.",
    },
    {
        "input_hint": "DB row: テーブル=CARD_APPLICATION, カラム=REQUESTED_CREDIT_LIMIT",
        "expected": "DBTable contains DBColumn; DBColumn DEFINES logical field when present.",
    },
    {
        "input_hint": "外部IF row: 外部与信IF sends LIMIT_AMT, 備考=別紙参照",
        "expected": "ExternalIF SENDS field; unresolved_mentions includes 別紙参照.",
    },
]


def prompt_for_region_type(region_type: str) -> str:
    return "\n".join(
        [
            DIRTY_EXCEL_REGION_EXTRACTION_PROMPT.strip(),
            REGION_TYPE_INSTRUCTIONS.get(region_type, "Extract only explicit nodes and relations."),
        ]
    )
