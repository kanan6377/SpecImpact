# Input Preparation Guide

SpecImpact works best when design documents expose structure explicitly. Use this guide before
ingesting legacy spreadsheets, wiki exports, or mixed-format design documents.

## Markdown

Prefer one artifact per top-level heading:

```md
# API: Payment Submit API

## Request fields
- paymentAmount
- merchantId

## Calls
- Fraud Gateway
```

Section headings can use common synonyms. For example, `入力項目`, `リクエスト項目`,
`API Parameters`, and `request parameters` are treated as `Request fields`.

Use `aliases.yml` for artifact and business-field name variants. Do not use artifact aliases to
rename section headings; section aliases and artifact aliases are separate concepts.

## Spreadsheet Migration Rules

Before loading CSV or Excel, reshape the source into a simple logical table:

- one worksheet per logical table
- one header row
- one value per cell
- no merged cells
- no free-layout forms
- no revision history block inside the data range
- item name, type, description, source, target, and notes should be explicit columns
- split cells that contain multiple fields into multiple rows
- move cross-sheet prose and別紙参照 into a separate Markdown note

Recommended columns:

```text
artifact_type, artifact_name, item_name, item_type, description, relation, target
```

If a legacy workbook cannot be reshaped safely, export the relevant sheet to Markdown and keep the
original workbook as a source attachment outside SpecImpact.

## Dirty Input Checklist

Before ingesting Excel files, check:

- Blank columns are removed
- Empty rows in the middle of tables are minimized
- Merged cells are avoided where possible
- Header rows are clear
- One logical table is placed in one sheet where possible
- Hidden sheets are reviewed
- Old definitions are removed or marked as obsolete

Excel取り込み前に、以下を確認してください。

- 空列を削除する
- 表の途中にある空行を減らす
- 可能なら結合セルを避ける
- ヘッダー行を明確にする
- 1シート1論理表に近づける
- 非表示シートを確認する
- 古い定義は削除するか obsolete と明記する

These rules are intentionally conservative. SpecImpact should miss less because the input structure
is explicit, not because a parser guessed aggressively.
