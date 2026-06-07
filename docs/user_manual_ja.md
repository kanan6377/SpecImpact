# SpecImpact 日本語利用マニュアル

このマニュアルは、SpecImpact を初めて使う人が、サンプル実行から自分の設計書の解析まで
進められるようにした手順書です。GUIを使う場合は [gui_manual_ja.md](gui_manual_ja.md) も
参照してください。

## 1. SpecImpactとは

SpecImpact は、LLMで設計書を evidence graph / GraphRAG に変換し、変更依頼から
「確認したほうがよい影響候補」を evidence 付きで出すローカルファーストのCLI/GUIツールです。

SpecImpact が出す結果は影響確定ではありません。`must_review` も「影響あり確定」ではなく、
「直接証拠や関係経路があるので必ず確認する」という意味です。最終判断は設計者、開発者、
テスト担当者が行います。

標準導線はLLM-firstです。Codex CLIを第一候補にし、OpenAI APIやOllamaも利用できます。
外部サービスへ設計書を送る場合は、provider設定と送信承認が必要です。解析データは作業
ディレクトリの `.specimpact/` に保存されます。

## 2. 動作環境

- Python 3.11 以上
- PowerShell またはコマンドプロンプト
- Git

以下の例は PowerShell 用です。

## 3. インストール

GitHubから取得して、editable install します。

```powershell
git clone https://github.com/kanan6377/SpecImpact.git
cd SpecImpact
python -m pip install -e .
specimpact --help
```

古い版をインストール済みの場合も、必ず `python -m pip install -e .` を実行し直してください。
`python -m specimpact` は古いインストールやカレントディレクトリの影響を受けやすいため、
通常利用では `specimpact` コマンドを使ってください。

GUIも使う場合:

```powershell
python -m pip install -e ".[gui]"
```

## 4. どの入口を選ぶか

| 入力の状態 | 使うコマンド |
| --- | --- |
| 初期導入をまとめて実行 | `specimpact onboard` |
| Markdown / text の設計書 | `specimpact ingest` |
| OpenAPI | `specimpact ingest-openapi` |
| SQL DDL | `specimpact ingest-ddl` |
| CSV | `specimpact ingest-csv` |
| 1行ヘッダーの表形式Excel | `specimpact ingest-excel` |
| 結合セル、複数表、改版履歴、同上、別紙参照があるExcel | `specimpact ingest-dirty-excel` |

迷った場合は、先にExcel診断を実行します。

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
```

## 5. サンプル1: Dirty Excelを試す

日本のSIer現場に近いExcelサンプルです。

```powershell
cd <repo-dir>
specimpact onboard .\examples\dirty_sier_excel\docs `
  --provider codex `
  --model default `
  --aliases .\examples\dirty_sier_excel\aliases.yml
specimpact change analyze .\examples\dirty_sier_excel\changes\利用限度額上限変更.md
specimpact impacts list
specimpact report --format markdown
specimpact export-obsidian .\vault
```

期待する流れ:

- `5 workbooks` のようにExcelが取り込まれる
- Change Atom に `利用限度額`、`requestedCreditLimit`、`REQUESTED_CREDIT_LIMIT` などが出る
- 画面項目、API項目、チェック仕様、DB項目、外部IF、境界値テストなどがレビュー候補になる
- 各候補に workbook、sheet、cell/range の evidence が付く
- `.\vault` をObsidianで開くと依存関係noteとCanvasを確認できる

LLMなしで挙動だけ確認する場合:

```powershell
specimpact onboard .\examples\dirty_sier_excel\docs `
  --no-llm `
  --aliases .\examples\dirty_sier_excel\aliases.yml
```

詳細は [../examples/dirty_sier_excel/README.md](../examples/dirty_sier_excel/README.md) を参照してください。

## 6. サンプル2: 構造が明確な設計書を試す

Markdown設計書のサンプルです。

```powershell
cd <repo-dir>
specimpact init
specimpact ingest .\examples\credit_card_enrollment\docs `
  --aliases .\examples\credit_card_enrollment\aliases.yml
specimpact analyze .\examples\credit_card_enrollment\changes\change_credit_limit.md
specimpact report --format markdown
specimpact why "カード入会申込API"
```

表形式Excelのサンプルです。

```powershell
cd <repo-dir>
specimpact init
specimpact ingest-excel .\examples\japanese_sier_excel\docs `
  --profile sier `
  --aliases .\examples\japanese_sier_excel\aliases.yml
specimpact analyze .\examples\japanese_sier_excel\changes\利用限度額_上限変更.md
specimpact report --format markdown
```

## 7. 自分のプロジェクトで使う

プロジェクトごとに作業ディレクトリを分けます。`.specimpact/` は現在のディレクトリに作られます。

```powershell
mkdir C:\work\my-system-impact
cd C:\work\my-system-impact
mkdir docs
mkdir changes
specimpact onboard .\docs --provider codex --model default --aliases .\aliases.yml
```

`onboard` は `.xlsx` を含む入力を dirty Excel、それ以外を Markdown/text として自動判定します。
外部送信したくない場合は `--no-llm` を付けます。

個別コマンドで進める場合、`docs\` に設計書を置きます。dirty Excel の場合:

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
specimpact ingest-dirty-excel .\docs --aliases .\aliases.yml
```

Markdownやtextの場合:

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
```

表形式Excelの場合:

```powershell
specimpact ingest-excel .\docs --profile sier --aliases .\aliases.yml
```

## 8. 変更依頼を書く

`changes\change_example.md` を作成します。先頭にMarkdown見出しを置いてください。

```markdown
# 変更依頼: 利用上限の変更

## 変更内容

入会申込画面の「利用限度額」の上限を999万円から9999万円に変更する。

## 確認したい観点

- 画面項目
- APIリクエスト
- 入力チェック
- DBカラム
- 外部連携
- 境界値テスト
```

解析します。

```powershell
specimpact change parse .\changes\change_example.md
specimpact analyze .\changes\change_example.md --llm-first
specimpact report --format markdown
```

自然言語を直接渡す場合:

```powershell
specimpact change analyze "入会申込画面の利用限度額上限を999万円から9999万円に変更"
```

LLMを使わない通常解析にしたい場合:

```powershell
specimpact analyze .\changes\change_example.md --no-llm
```

## 9. レポートの読み方

主な項目は以下です。

| 項目 | 意味 |
| --- | --- |
| `artifact_id` | ツール内部で使う安定ID |
| `display_name` | 人が読む表示名 |
| `review_priority` | レビュー優先度 |
| `evidence_strength` | 証拠の明示度 |
| `match_type` | 完全一致、alias、一部推論などの一致方法 |
| `relation_distance` | 変更対象から候補までの関係距離 |
| `reason` | 候補に挙がった理由 |
| `relation_paths` | 変更対象から候補までの経路 |
| `evidence_ids` | 根拠レコードのID |
| `needs_review` | 人による確認が必要か |

`review_priority` の意味:

| 値 | 意味 |
| --- | --- |
| `must_review` | 直接証拠と関係経路があり、必ず確認する |
| `should_review` | 関係が近く、確認したほうがよい |
| `may_review` | 弱い一致やLLM仮説。必要に応じて確認する |
| `hidden` | 証拠が弱い。Markdownレポートには通常表示されない |

`evidence_strength` は確率ではありません。SpecImpact は未較正の confidence score を出しません。

## 10. なぜ候補に入ったか確認する

表示名、alias、内部IDを指定できます。

```powershell
specimpact why "カード入会申込API"
specimpact why api.card_application.submit
specimpact why-not "本人確認サービス"
```

証拠を直接見る場合:

```powershell
specimpact inspect evidence
specimpact inspect evidence <evidence_id>
```

## 11. レビュー結果を保存する

Dirty ExcelやLLM抽出では、提案をそのまま確定せず、review status を保存します。

Graph proposal:

```powershell
specimpact graph proposals list
specimpact graph proposals accept <proposal_id>
specimpact graph proposals reject <proposal_id>
```

Alias:

```powershell
specimpact aliases suggest
specimpact aliases review
specimpact aliases confirm <candidate_id>
specimpact aliases reject-candidate <candidate_id>
```

Relation:

```powershell
specimpact relations list
specimpact relations set-status <relation_id> confirmed
specimpact relations set-status <relation_id> rejected
```

Impact:

```powershell
specimpact impacts list
specimpact impacts set-status <impact_id> accepted --reason "修正対象"
specimpact impacts set-status <impact_id> needs_investigation --reason "別紙参照先の確認が必要"
specimpact impacts set-status <impact_id> closed --reason "実装とテスト完了"
```

## 12. aliasファイルを書く

表記揺れがある場合は `aliases.yml` を用意します。

```yaml
aliases:
  api.card_application.submit:
    canonical_type: API
    aliases:
      - 入会申込API
      - cardApplicationSubmit

  field.requested_credit_limit:
    canonical_type: BusinessField
    aliases:
      - 利用限度額
      - requestedCreditLimit
      - REQUESTED_CREDIT_LIMIT
      - LIMIT_AMT
```

注意:

- alias は別の内部IDと重複させないでください。
- 型が異なる artifact 間でも同じ alias は避けてください。
- `canonical_type` は `API`、`Table`、`BusinessField` などの許可された型を指定します。

## 13. 推奨Markdown形式

Markdown設計書は、1つのartifactを1つのトップレベル見出しで書くと解析しやすくなります。

```markdown
# API: Payment Submit API

## Request fields
- paymentAmount
- merchantId

## Calls
- Fraud Gateway
```

```markdown
# Screen: Payment Entry Screen

## Fields
- paymentAmount
- merchantId

## Calls
- Payment Submit API
```

代表的なartifact:

- `API`
- `Screen`
- `Table`
- `Column`
- `ValidationRule`
- `ExternalIF`
- `TestCase`
- `Batch`
- `Document`

代表的な関係見出し:

- `Request fields`
- `Response fields`
- `Reads`
- `Writes`
- `Displays`
- `Validates`
- `Sends`
- `Receives`
- `Calls`
- `Covers`
- `Asserts`

`入力項目`、`リクエスト項目`、`API Parameters`、`request parameters` など一部の同義見出しも扱えます。
artifact名や項目名の表記揺れは `aliases.yml`、section heading の同義語はparser側のsection aliasです。
両者を混同しないでください。

## 14. LLM provider

LLM-firstが標準導線です。Codex CLIを第一候補にし、OpenAI APIやOllamaも利用できます。

```powershell
specimpact llm status
specimpact llm configure --provider codex --model default
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm disable
```

OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は外部送信確認が必要です。
localhost Ollama と local embeddings はローカルで動作します。CI、debug、秘匿性の強い案件では
`--no-llm` を使います。

## 15. よくあるエラー

### `specimpact` コマンドが見つからない

リポジトリルートで再インストールしてください。

```powershell
cd <repo-dir>
python -m pip install -e .
```

### v2コマンドが見えない

古いインストールを拾っています。`specimpact --help` に `ingest-dirty-excel`、`change`、
`impacts` が表示されるか確認してください。表示されない場合は再インストールしてください。

### `No analysis run exists`

先に設計書を読み込み、変更依頼を解析してください。

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
specimpact analyze .\changes\change_example.md
```

### `Ambiguous alias`

同じaliasが複数の内部IDに割り当てられています。`aliases.yml` の重複を解消してください。

### `Invalid Excel source`

拡張子だけでなく、ファイルが有効な `.xlsx` workbook であることを確認してください。
表形式ではないExcelは `ingest-dirty-excel` を使ってください。

## 16. 状態確認とリセット

現在の状態:

```powershell
specimpact status
specimpact doctor --privacy
```

最初からやり直す場合は、作業ディレクトリ内の `.specimpact/` を削除してから
`specimpact init` から再実行します。削除対象が正しい作業ディレクトリ内であることを必ず
確認してください。

## 17. 補助機能

Obsidian review vault:

```powershell
specimpact export-obsidian .\vault
specimpact export-obsidian .\vault --report-only
```

通常の `export-obsidian` は `SpecImpact/Dashboard.md`、`Artifacts`、`Evidence`、`Changes`、
`Canvases` を生成します。`--report-only` は旧形式のMarkdownレポートコピーです。

graph baseline:

```powershell
specimpact baseline create before
specimpact graph diff before
```

review import:

```powershell
specimpact review import .\review-results.json
```

Neo4j backend は任意機能です。通常利用ではlocal backendのまま使用してください。

## 18. 開発者向け

```powershell
python -m pip install -e ".[dev,gui]"
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```

`release-check` はOSS公開用の品質gateです。通常の変更影響レビューでは不要です。
