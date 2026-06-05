# SpecImpact

SIerのExcel地獄な設計書から、変更影響を証拠つきで管理する
ローカルファーストOSSです。

SpecImpact は、結合セル、表記揺れ、複数表混在、別紙参照を含む legacy Excel を
セル番地つき evidence と region に分解し、LLMまたはローカルルールで
画面・API・DB・外部IF・入力チェック・テストの関係候補を抽出します。
出力は影響確定ではなく、証拠つきレビュー仮説です。人間の採否判断を蓄積し、
次回以降の影響分析に活用します。

## Excel Demo

```powershell
python -m pip install -e .
specimpact init
specimpact ingest-excel ./examples/japanese_sier_excel/docs --profile sier --aliases ./examples/japanese_sier_excel/aliases.yml
specimpact analyze ./examples/japanese_sier_excel/changes/利用限度額_上限変更.md
specimpact report --format markdown
specimpact report --format excel
```

Dirty Excel v2 flow:

```powershell
python -m pip install -e .
specimpact init
specimpact ingest-dirty-excel ./examples/dirty_sier_excel/docs --aliases ./examples/dirty_sier_excel/aliases.yml
specimpact graph proposals list
specimpact aliases suggest --llm
specimpact change parse ./examples/dirty_sier_excel/changes/利用限度額上限変更.md
specimpact analyze ./examples/dirty_sier_excel/changes/利用限度額上限変更.md --llm-first
specimpact impacts list
```

Latest release: [v0.1.0-alpha](https://github.com/kanan6377/SpecImpact/releases/tag/v0.1.0-alpha)

変更依頼:

> 入会申込画面の「利用限度額」の上限を999万円から9999万円に変更する。

SpecImpact は以下をレビュー候補として出します。

- 入会申込画面
- 入会申込API
- REQUESTED_CREDIT_LIMIT カラム
- 利用限度額入力チェック
- 外部与信IF
- 境界値テスト

それぞれについて、Excelのファイル名・シート名・行番号・セル位置を根拠として表示します。

Excelを取り込む前に、状態診断だけを見ることもできます。

```powershell
specimpact excel inspect ./examples/japanese_sier_excel/docs
```

出力例:

```text
Excel Health Check

Workbooks: 6
Sheets: 6
Detected artifacts: 14
Possible relations: 14

Warnings:
- merged cells: 0
- hidden sheets: 0
- revision history sheets: 0
- duplicate item names: 10
- alias candidates: 4
- 複数のヘッダー候補があるシートがあります。
```

## Why

Design changes rarely touch one file. They hit APIs, screens, tables, validations, external
interfaces, and tests. SpecImpact makes that blast radius inspectable:

- local-first graph extraction
- evidence quotes with file and line numbers
- `must_review` / `should_review` / `may_review` candidates
- Graph Explorer for relation review
- optional LLM extraction and batch reranking
- privacy checks before external transmission

## What You Get

Input change request:

```md
# Change: requestedCreditLimit upper bound

requestedCreditLimit の上限を変更する。
```

SpecImpact output:

```md
must_review:
- カード入会申込API
  reason: request field として requestedCreditLimit を使っている
  path: change -> requestedCreditLimit <- REQUEST_FIELD - api.card_application.submit
  evidence: docs/05_card_application_api.md:6-15

should_review:
- 希望利用限度額チェック
  reason: requestedCreditLimit を validation で参照している
  path: change -> requestedCreditLimit <- VALIDATES - validation.credit_limit
  evidence: docs/07_validation_rules.md:4-7
```

Reports list review candidates, not confirmed impacts. `must_review` means "must be checked",
not "confirmed affected".

![Graph Explorer](docs/images/gui/graph-explorer.png)

Default mode:

```text
LLM: disabled
External transmission: none
Backend: local JSONL
Embeddings: local unless explicitly rebuilt with a remote provider
```

Japanese user manual: [docs/user_manual_ja.md](docs/user_manual_ja.md)

Local GUI manual: [docs/gui_manual_ja.md](docs/gui_manual_ja.md)

## Quickstart

Excel Impact Review MVP の最短デモ:

```powershell
python -m pip install -e .
specimpact init
specimpact ingest-excel ./examples/japanese_sier_excel/docs --profile sier --aliases ./examples/japanese_sier_excel/aliases.yml
specimpact analyze ./examples/japanese_sier_excel/changes/利用限度額_上限変更.md
specimpact report --format markdown
specimpact report --format excel
```

従来のMarkdown設計書サンプル:

```powershell
python -m pip install -e .
specimpact init
specimpact ingest ./examples/credit_card_enrollment/docs --aliases ./examples/credit_card_enrollment/aliases.yml
specimpact analyze ./examples/credit_card_enrollment/changes/change_credit_limit.md
specimpact report --format markdown
specimpact why "カード入会申込API"
```

Local state is stored under `.specimpact/`.

## Optional Local GUI

```powershell
python -m pip install -e ".[gui]"
specimpact gui
```

Useful options:

```powershell
specimpact gui --port 8765
specimpact gui --project C:\work\my-system-impact
specimpact gui --no-open-browser
```

The GUI binds only to `127.0.0.1`. It has no LAN exposure option. Registered projects remain
independent local workspaces. The guided sample copies `examples/credit_card_enrollment` before it
runs, so the original sample is not modified.

The GUI is built as a local impact lab:

- Dashboard launchpad with graph counts, privacy status, LLM mode, and job history
- Guided demo
- Ingest for Markdown, OpenAPI, DDL, CSV, Excel, and managed uploads
- Analyze / Report with evidence and LLM advisory reasons
- Graph Explorer with relation status updates
- Settings for local backend, embeddings, OpenAI, Ollama, Codex CLI, and fake providers

## Extraction Model

Markdown extraction is convention-based and inspectable. Headings such as `API:`, `Screen:`,
`Table:`, `ValidationRule:`, and `ExternalIF:` define artifacts. Sections such as `Request fields`,
`Reads`, `Writes`, `Displays`, `Sends`, and `Covers` define relations. Plain text matches are kept
as conservative mentions.

Structured loaders cover straightforward OpenAPI, DDL, CSV, and clean Excel definitions. See
[docs/structured_loaders.md](docs/structured_loaders.md). For messy enterprise spreadsheets and
legacy design documents, use `ingest-dirty-excel` and start with
[docs/input_preparation.md](docs/input_preparation.md).

## Optional AI

Rule extraction remains the default. Optional LLM extraction and semantic retrieval can be enabled
independently:

```powershell
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm configure --provider codex --model default
specimpact llm status
specimpact llm disable
specimpact embeddings rebuild --provider local
specimpact analyze ./change.md --no-llm
```

OpenAI, Codex CLI, remote Ollama, and OpenAI embeddings require per-command confirmation or `--yes`.
The Codex provider invokes a logged-in `codex exec` subprocess with an ephemeral session, an empty
temporary working directory, a read-only sandbox, and batched reranking. Localhost Ollama and local
embeddings stay on the machine. OpenAI API keys are read only from `OPENAI_API_KEY`.

## Review Workflow

```powershell
specimpact aliases suggest
specimpact aliases list
specimpact relations list
specimpact relations set-status rel.api.card_application.submit.request_field confirmed
specimpact inspect graph
specimpact inspect evidence ev.api.card_application.submit.request_field
specimpact why-not "本人確認サービス"
specimpact doctor --privacy
```

`why` and `why-not` are backed by the latest run's `trace.jsonl`. Evaluation metrics assist review
quality checks; they are not confidence scores.

## Optional Integrations

```powershell
specimpact backend set neo4j --uri bolt://localhost:7687
specimpact export-obsidian ./vault
specimpact review import ./examples/credit_card_enrollment/reviews/change_credit_limit.review.json
specimpact baseline create before
specimpact graph diff before
specimpact backend set local
```

The local JSONL backend remains the default. See [docs/integrations.md](docs/integrations.md).

## Development

```powershell
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check ./examples/evaluation/release_cases.yml
```

See [docs/roadmap.md](docs/roadmap.md), [docs/phase_status.md](docs/phase_status.md), and
[docs/release.md](docs/release.md).

## Evaluation Scope

The release dataset is useful for regression control, not a claim of final impact correctness.

## Limitations

SpecImpact does not try to fully understand every Excel layout.

Current v1 loader works best with:

- Table-like Excel design documents
- Clear header rows
- One logical table per sheet
- Japanese SIer-style screen/API/DB/IF/test definition sheets

Use `ingest-dirty-excel` for:

- Merged-cell workbook layouts
- Revision history and tables in the same sheet
- Multiple logical regions per sheet
- Japanese labels mixed with API/DB physical names
- Evidence review before accepting LLM or inferred graph proposals

Still not supported well:

- Diagrams and arrows
- ER diagrams as images
- Completely unstructured documents

## 制限事項

SpecImpact は、あらゆるExcel方眼紙を完全解析するツールではありません。

現在のMVPが得意なもの:

- 表形式に近いExcel設計書
- ヘッダー行が明確なシート
- 1シート1論理表に近い構成
- 日本SIerでよくある画面/API/DB/IF/テスト定義書

まだ苦手なもの:

- 結合セルだらけの自由レイアウト
- 図形や矢印の意味理解
- 画像として貼られたER図
- 複雑な方眼紙レイアウト
- 完全に非構造なExcel

Known evaluation limits:

- synthetic sample heavy
- no large legacy Excel corpus yet
- no real enterprise design document benchmark
- metrics are for review-candidate recall, not final impact correctness
- dirty input, false positives, and alias collisions should be tracked separately during adoption

