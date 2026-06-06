# SpecImpact CLI リファレンス

このページは、通常利用で使うCLIコマンドの早見表です。最初の操作手順は
[user_manual_ja.md](user_manual_ja.md) を参照してください。

## 基本

| コマンド | 用途 |
| --- | --- |
| `specimpact init` | 現在のディレクトリに `.specimpact/` を作成する |
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

## 任意のLLMとembeddings

```powershell
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm configure --provider codex --model default
specimpact llm configure --provider fake --model fake
specimpact llm status
specimpact llm disable
specimpact embeddings rebuild --provider local
```

外部プロバイダは標準で無効です。OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は
外部送信確認が必要です。

## GUI

```powershell
python -m pip install -e ".[gui]"
specimpact gui
specimpact gui --port 8765
specimpact gui --project C:\work\my-system-impact
specimpact gui --no-open-browser
```

GUIは `127.0.0.1` のみにbindします。

## 開発・リリース確認

```powershell
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```
