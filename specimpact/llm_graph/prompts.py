from __future__ import annotations

DIRTY_EXCEL_REGION_EXTRACTION_PROMPT = """
You are a SpecImpact extraction backend for Japanese SIer Excel design documents.
Return JSON only, matching the supplied schema.
Extract design nodes and relations from one cell-addressed region.
Every node and edge must cite evidence_ids from the supplied payload.
Use only supplied cells_markdown and evidence. Never invent workbook content.
Do not treat revision history, cover sheets, approval stamps, or comments-only blocks as
design facts.
Put references such as 同上, 上記と同じ, 別紙参照, 別シート参照, see another sheet into
unresolved_mentions
unless the referenced row or sheet is explicitly present in the same region payload.
Use explicit when a row/heading directly states the relation. Use layout_inferred or
cross_reference_inferred when merged headers, parent headings, or notes imply it.
"""


REGION_TYPE_INSTRUCTIONS = {
    "screen_item_table": """
Read this as a screen item definition table.
Create Screen nodes for screen names/IDs and ScreenField nodes for item names or physical names.
Common columns: 画面ID, 画面名, 項目ID, 項目名, 表示名, 物理名, 型, 桁数, 必須, 入力可否,
初期値, チェック内容, 呼び出すAPI, 備考.
Merged parent headers usually define the current Screen or section for child rows.
Put field attributes such as required flag, length, type, default value, input constraint,
and notes into node.properties.
Create Screen DISPLAYS ScreenField. If the row names an API, create Screen CALLS API.
If the row contains validation/check text, create ValidationRule VALIDATES ScreenField.
Do not convert logical and physical names to aliases unless the same row directly maps them.
""",
    "validation_block": """
Read this as an input validation or business rule block.
Create ValidationRule nodes and target ScreenField/APIField nodes.
Common columns: チェックID, チェック名, 対象項目, 項目名, 物理名, 必須, 桁数, 上限, 下限,
チェック内容, エラーID, エラーメッセージ, 備考.
Upper/lower bounds, digit length, required checks, format rules, and error messages are properties.
Preserve boundary values exactly as written when they appear in evidence.
Create ValidationRule VALIDATES target field only when the target is named in the row or
parent header.
Treat 同上 and 上記と同じ as unresolved unless the referenced target is obvious in the same region.
""",
    "api_mapping_table": """
Read this as an API request/response mapping table.
Create API nodes and APIField nodes. Common columns: API名, エンドポイント, 区分, request/response,
項目名, 論理名, 物理名, JSON名, 型, 桁数, 必須, マッピング元, マッピング先, 備考.
Request rows create API REQUEST_FIELD APIField. Response rows create API RESPONSE_FIELD APIField.
If a row maps a screen field or DB column to an API field, create maps_to or DEFINES only when both
sides are explicitly named in the row.
Japanese logical names and camelCase physical names are alias candidates, not confirmed aliases.
Keep external references and 別紙参照 in unresolved_mentions.
""",
    "db_mapping_table": """
Read this as a database table/column definition or mapping.
Create DBTable and DBColumn nodes. Common columns: テーブル名, テーブル物理名, カラム名,
カラム物理名, 論理名, 項目名, 型, 桁数, NULL, PK, FK, 初期値, 備考.
Create DBTable contains DBColumn. If a logical field or screen/API field is explicitly mapped,
create DBColumn DEFINES that field.
Physical names such as REQUESTED_CREDIT_LIMIT should remain DBColumn names or aliases.
Do not infer application behavior from DB remarks alone; put uncertain notes into warnings.
""",
    "external_if_table": """
Read this as an external interface item table.
Create ExternalIF nodes for partner systems, services, or IF names, and APIField/BusinessField nodes
for sent or received items.
Common columns: IF名, 外部システム, 送受信, 送信項目, 受信項目, 項目名, 物理名, 型, 桁数,
必須, 変換, 備考.
Direction controls SENDS or RECEIVES. Keep partner system names as ExternalIF nodes.
別紙参照 and separate interface definition references must go to unresolved_mentions unless
included.
""",
    "test_case_table": """
Read this as a test case or boundary test table.
Create TestCase nodes and COVERS relations to fields, validation rules, APIs, DB columns,
or external IFs.
Common columns: 試験ID, テストケースID, テスト名, 対象項目, 確認観点, 入力値, 期待結果,
境界値, 正常/異常, 備考.
Boundary values and expected errors are important properties. Preserve values exactly.
Create COVERS only when the target is named in the row or parent heading.
""",
}


DIRTY_EXCEL_FEW_SHOTS = [
    {
        "region_type": "screen_item_table",
        "input_hint": (
            "Row has 画面名=入会申込画面, 項目名=利用限度額, 物理名=requestedCreditLimit, "
            "必須=Y, 桁数=9."
        ),
        "expected": (
            "Create Screen 入会申込画面, ScreenField 利用限度額 with alias requestedCreditLimit "
            "and properties required/length, then Screen DISPLAYS ScreenField."
        ),
    },
    {
        "region_type": "validation_block",
        "input_hint": (
            "Row has チェック名=利用限度額上限チェック, 対象項目=利用限度額, 上限=999万円, "
            "エラーメッセージ=上限を超えています."
        ),
        "expected": (
            "Create ValidationRule with upper_bound/error_message properties and VALIDATES "
            "the target field. Cite row evidence."
        ),
    },
    {
        "region_type": "api_mapping_table",
        "input_hint": (
            "Row has API名=入会申込API, 区分=request, 論理名=利用限度額, "
            "物理名=requestedCreditLimit."
        ),
        "expected": (
            "Create API 入会申込API and APIField requestedCreditLimit, then API REQUEST_FIELD "
            "APIField. Logical name is an alias candidate."
        ),
    },
    {
        "region_type": "db_mapping_table",
        "input_hint": (
            "Row has テーブル物理名=CARD_APPLICATION, カラム物理名=REQUESTED_CREDIT_LIMIT, "
            "論理名=利用限度額."
        ),
        "expected": (
            "Create DBTable CARD_APPLICATION, DBColumn CARD_APPLICATION.REQUESTED_CREDIT_LIMIT, "
            "and DBTable contains DBColumn. Add logical name as alias/property when evidenced."
        ),
    },
    {
        "region_type": "external_if_table",
        "input_hint": "Row has IF名=信用審査IF, 送受信=送信, 物理名=LIMIT_AMT, 備考=別紙参照.",
        "expected": (
            "Create ExternalIF 信用審査IF and field LIMIT_AMT, then ExternalIF SENDS field. "
            "Put 別紙参照 into unresolved_mentions."
        ),
    },
    {
        "region_type": "test_case_table",
        "input_hint": (
            "Row has テスト名=利用限度額境界値, 対象項目=利用限度額, 入力値=9999万円, "
            "期待結果=正常."
        ),
        "expected": (
            "Create TestCase and COVERS target field/rule. Preserve boundary input and expected "
            "result in properties."
        ),
    },
]


def prompt_for_region_type(region_type: str) -> str:
    return "\n".join(
        [
            DIRTY_EXCEL_REGION_EXTRACTION_PROMPT.strip(),
            REGION_TYPE_INSTRUCTIONS.get(
                region_type,
                "Extract only explicit nodes and relations.",
            ).strip(),
        ]
    )
