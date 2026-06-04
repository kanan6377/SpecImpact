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

Run a quick cleanup before ingest:

- duplicated headers are renamed
- blank columns are removed
-途中空行 inside the table are removed
- Japanese, English, snake_case, and camelCase aliases are registered
-同名項目 that refer to different concepts have distinct aliases
- rejected relations from prior review are preserved before re-ingest

These rules are intentionally conservative. SpecImpact should miss less because the input structure
is explicit, not because a parser guessed aggressively.
