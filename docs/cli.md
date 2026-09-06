# SpecImpact CLI リファレンス

## 仕様分析の履歴

`analyze`と`analyze --llm-first`は共通の仕様分析カーネルの結果も保存します。
対応するラベル付き長さ制約は既存レポートに反映し、それ以外は
`legacy_candidate_not_a_verified_constraint_comparison`を付けたレビュー候補として保持します。

```powershell
specimpact analysis show
specimpact analysis replay
specimpact analysis export .\analysis-snapshot.json
specimpact analysis import .\analysis-snapshot.json
specimpact analysis decide <case-id> accepted --actor reviewer --reason "Checked original"
```

`show`、`replay`、`export`は分析IDまたはreport IDを任意指定できます（既定は`latest`）。
exportには原典のEvidence引用が含まれます。設計書と同じ扱いで保管してください。
importは再検証してから保存し、従来のJSONLグラフを書き換えません。

このページは、通常利用で使うCLIコマンドの早見表です。最初の操作手順は
[user_manual_ja.md](user_manual_ja.md) を参照してください。

## 基本

| コマンド | 用途 |
| --- | --- |
| `specimpact init` | 現在のディレクトリに `.specimpact/` を作成する |
| `specimpact onboard <docs>` | LLM provider設定、設計書投入、graph構築、任意のObsidian出力をまとめて実行する |
| `specimpact status` | 取り込み件数、最新run、設定状態を表示する |
| `specimpact doctor --privacy` | 外部送信やbackend設定を確認する |
| `specimpact analyze <change.md>` | 変更依頼を解析し、レビュー候補を作成する |
| `specimpact report --format markdown` | 最新runのMarkdownレポートを表示する |
| `specimpact report --format json` | 最新runのJSONレポートを表示する |
| `specimpact report --format excel` | 最新runのExcelレポートを書き出す |
| `specimpact why <name-or-id>` | 候補に入った理由を表示する |
| `specimpact why-not <name-or-id>` | 候補に入らなかった理由をtraceから表示する |

## 取り込み

| 入力 | コマンド |
| --- | --- |
| Markdown / text | `specimpact ingest .\docs --aliases .\aliases.yml` |
| dirty Excel | `specimpact ingest-dirty-excel .\docs --aliases .\aliases.yml` |
| dirty Excel互換形式 | `specimpact ingest .\docs --mode dirty-excel --aliases .\aliases.yml` |
| clean Excel | `specimpact ingest-excel .\docs --profile sier --aliases .\aliases.yml` |
| OpenAPI | `specimpact ingest-openapi .\openapi.yml` |
| SQL DDL | `specimpact ingest-ddl .\schema.sql` |
| CSV | `specimpact ingest-csv .\fields.csv` |

`onboard` は `.xlsx` を含む入力を dirty Excel、それ以外を Markdown/text として自動判定します。
標準providerは Codex CLI です。

```powershell
specimpact onboard .\docs --provider codex --model default --aliases .\aliases.yml
specimpact onboard .\docs --no-llm --aliases .\aliases.yml
specimpact onboard .\docs --obsidian-vault .\vault --aliases .\aliases.yml
```

`ingest-excel` は1行ヘッダーの表形式Excel向けです。結合セル、複数表混在、改版履歴ブロック、
別紙参照、同上表記がある場合は `ingest-dirty-excel` を使います。

## Excel診断

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
specimpact excel lint .\docs
```

`inspect` は表形式Excel向けのHealth Checkです。`classify` はdirty Excel向けにsheet分類と
region検出結果をJSONで表示します。`lint` は警告がある場合に非ゼロ終了します。

## Dirty Excelレビュー

```powershell
specimpact graph proposals list
specimpact graph proposals accept <proposal_id>
specimpact graph proposals reject <proposal_id>
```

dirty Excel取り込みでは、LLMまたはローカルルールの抽出結果を graph proposal として保存します。
提案は evidence ID を持ち、accept/reject できます。LLM由来の提案は、人間が確認するまで
確定扱いにしないでください。

## Aliasレビュー

```powershell
specimpact aliases suggest
specimpact aliases suggest --llm
specimpact aliases review
specimpact aliases confirm <candidate_id>
specimpact aliases reject-candidate <candidate_id>
specimpact aliases list
specimpact aliases add <target_id> <alias>
specimpact aliases remove <target_id> <alias>
```

旧形式のalias候補には以下も使えます。

```powershell
specimpact aliases approve <target_id> <alias>
specimpact aliases reject <target_id> <alias>
```

## Change Atomとimpact管理

```powershell
specimpact change parse .\changes\change.md
specimpact change analyze "利用限度額の上限を999万円から9999万円に変更"
specimpact change analyze .\changes\change.md
specimpact changes list
specimpact changes show <change_id>
specimpact analyze .\changes\change.md --llm-first
specimpact impacts list
specimpact impacts list --change <change_id>
specimpact impacts set-status <impact_id> accepted --reason "修正対象"
```

impact status は以下のいずれかです。

- `unreviewed`
- `accepted`
- `rejected`
- `needs_investigation`
- `implemented`
- `tested`
- `closed`

## Relationレビュー

```powershell
specimpact relations list
specimpact relations set-status <relation_id> confirmed
specimpact relations set-status <relation_id> rejected
specimpact inspect graph
specimpact inspect artifact <name-or-id>
specimpact inspect evidence
specimpact inspect evidence <evidence_id>
```

relation status は `confirmed`、`unconfirmed`、`rejected` です。

## LLM provider と embeddings

```powershell
specimpact llm configure --provider codex --model default
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm configure --provider fake --model fake
specimpact llm status
specimpact llm disable
specimpact embeddings rebuild --provider local
```

LLM-firstが標準導線です。OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は外部送信確認が
必要です。秘匿性の強い案件、CI、debugでは `--no-llm` を使います。

## Obsidian

```powershell
specimpact export-obsidian .\vault
specimpact export-obsidian .\vault --report-only
```

通常の `export-obsidian` は `SpecImpact/Artifacts`、`Evidence`、`Changes`、`Canvases`、
`Dashboard.md` を含むreview vaultを生成します。`--report-only` は旧形式のMarkdownレポートコピーです。

## GUI

```powershell
python -m pip install -e ".[gui]"
specimpact gui
specimpact gui --port 8765
specimpact gui --project C:\work\my-system-impact
specimpact gui --no-open-browser
```

GUIは `127.0.0.1` のみにbindします。

## MCP server

```powershell
python -m pip install -e ".[mcp]"
specimpact mcp --stdio --project C:\work\my-system-impact
```

MCPはstdio専用です。`--project`がworkspace境界になり、その外側のpathは受け付けません。
長時間処理は永続Job IDを返すため、`get_job`または`list_jobs`で追跡します。

Agent host導入確認:

```powershell
specimpact agent doctor --host cursor --project C:\work\my-system-impact
```

`agent hook`はPlugin lifecycle用の非表示commandです。手動実行は不要です。本文を保存せず、
workspace内で変更された設計sourceのpathとhashだけを通知ledgerへ記録します。

## 開発・リリース確認

```powershell
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```

## 公開実設計書ベンチマーク

Fintanの固定commitから、Manifestで指定した21冊のWorkbookだけを取得します。取得処理はgit objectを使用し、リポジトリ全体をCheckoutしません。出力にはSHA-256付き`provenance.json`が生成されます。

```powershell
specimpact benchmark fetch-fintan .\temp\fintan-corpus
```

取得済みCorpusを決定論的に評価します。`--workspace`は空のWorkspaceを指定してください。

```powershell
specimpact benchmark run-fintan .\temp\fintan-corpus `
  --workspace .\temp\fintan-workspace `
  --aliases .\examples\fintan_benchmark\aliases.yml `
  --change .\examples\fintan_benchmark\change_project_name_length.md `
  --expected .\examples\fintan_benchmark\expected_project_name_length.json
```

このベンチマークは最終影響を自動確定しません。Evidence、Graph path、Verifier結果をレビュー候補として出力します。原典はFintanコンテンツ使用許諾条項に従い、詳細は[実験報告書](reviews/fintan-compatibility-benchmark.md)を参照してください。
