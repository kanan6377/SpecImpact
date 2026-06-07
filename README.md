# SpecImpact

SIerのExcel地獄な設計書をLLMで読解し、変更影響を証拠付きで管理する
ローカルファーストOSSです。

SpecImpact は、設計書をLLMで evidence graph / GraphRAG に変換し、変更依頼から
「確認したほうがよい画面・API・DB・外部IF・入力チェック・テスト」を根拠付きで一覧化します。
出力は影響確定ではなくレビュー候補です。最終判断は人間が行い、採否判断をローカルに蓄積します。

## 何ができるか

- Codex CLI、OpenAI API、Ollama を使って設計書を構造把握する
- Markdown、OpenAPI、DDL、CSV、Excelから設計要素と関係を抽出する
- 結合セル、表記揺れ、複数表混在、別紙参照を含む汚いExcelをセル番地付きで取り込む
- 自然言語の変更依頼を Change Atom に分解し、影響候補を `must_review` / `should_review` / `may_review` に分類する
- すべての候補に、ファイル名、シート名、セル番地、行番号などの evidence を残す
- alias 候補、graph 提案、impact 判断をレビューして保存する
- Obsidian Vault / Canvas に設計依存関係と影響レビューを出力する
- CLI と localhost 限定GUIのどちらでも使う

標準導線はLLM-firstです。ただし、外部サービスへ設計書を送る場合は明示設定と承認が必要です。

```text
Standard provider: Codex CLI recommended
External transmission: preview + approval
Backend: local JSONL
State directory: .specimpact/
Fallback: --no-llm
```

## インストール

現時点ではGitHubからの利用を想定しています。

```powershell
git clone https://github.com/kanan6377/SpecImpact.git
cd SpecImpact
python -m pip install -e .
specimpact --help
```

古い版をインストール済みの場合は、必ず上の `python -m pip install -e .` を実行し直してください。
`python -m specimpact` は現在のディレクトリや古いインストール状態の影響を受けるため、
通常は `specimpact` コマンドを使います。

## まず試す: LLM-first Dirty Excelサンプル

日本のSIer現場でありがちな、結合セル、表記揺れ、別紙参照、同上、境界値テストを含むExcel
サンプルです。

```powershell
specimpact onboard .\examples\dirty_sier_excel\docs `
  --provider codex `
  --model default `
  --aliases .\examples\dirty_sier_excel\aliases.yml
specimpact change analyze .\examples\dirty_sier_excel\changes\利用限度額上限変更.md
specimpact impacts list
specimpact report --format markdown
specimpact export-obsidian .\vault
```

このサンプルでは、利用限度額上限変更に対して、画面項目、API項目、チェック仕様、DB項目、
外部IF、境界値テストなどをレビュー候補として扱う流れを確認できます。Obsidianを使う場合は
`.\vault` をVaultとして開くと、Artifacts、Evidence、Changes、Canvas を探索できます。

ローカルfallbackだけで試す場合:

```powershell
specimpact onboard .\examples\dirty_sier_excel\docs `
  --no-llm `
  --aliases .\examples\dirty_sier_excel\aliases.yml
```

詳細な見方は [examples/dirty_sier_excel/README.md](examples/dirty_sier_excel/README.md) を参照してください。

## もう一つの入口: きれいな設計書

Markdownや表形式Excelなど、構造がはっきりした入力では従来の ingest を使います。

```powershell
specimpact init
specimpact ingest .\examples\credit_card_enrollment\docs `
  --aliases .\examples\credit_card_enrollment\aliases.yml
specimpact analyze .\examples\credit_card_enrollment\changes\change_credit_limit.md
specimpact report --format markdown
specimpact why "カード入会申込API"
```

表形式Excelだけを取り込む場合:

```powershell
specimpact ingest-excel .\examples\japanese_sier_excel\docs `
  --profile sier `
  --aliases .\examples\japanese_sier_excel\aliases.yml
```

## 自分の設計書で使う

プロジェクトごとに作業ディレクトリを分けるのが基本です。`.specimpact/` は現在の
ディレクトリに作成されます。

```powershell
mkdir C:\work\my-system-impact
cd C:\work\my-system-impact
specimpact onboard .\docs --provider codex --model default --aliases .\aliases.yml
```

`onboard` は入力が `.xlsx` を含む場合は dirty Excel、そうでない場合は Markdown/text として取り込みます。
外部送信したくない場合は `--no-llm` を付けてください。

従来の個別コマンドを使う場合:

```powershell
specimpact init
specimpact llm configure --provider codex --model default
```

入力の種類でコマンドを選びます。

| 入力 | 推奨コマンド |
| --- | --- |
| Markdown / text | `specimpact ingest .\docs --aliases .\aliases.yml` |
| OpenAPI | `specimpact ingest-openapi .\openapi.yml` |
| SQL DDL | `specimpact ingest-ddl .\schema.sql` |
| CSV | `specimpact ingest-csv .\fields.csv` |
| 1行ヘッダーの表形式Excel | `specimpact ingest-excel .\docs --profile sier --aliases .\aliases.yml` |
| 結合セルや複数表を含む汚いExcel | `specimpact ingest-dirty-excel .\docs --aliases .\aliases.yml` |

Excelを取り込む前に状態だけ見る場合:

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
```

## レビューの進め方

```powershell
specimpact change analyze "入会申込画面の利用限度額上限を999万円から9999万円に変更"
specimpact graph proposals list
specimpact graph proposals accept <proposal_id>
specimpact aliases suggest
specimpact aliases review
specimpact aliases confirm <candidate_id>
specimpact relations list
specimpact impacts list
specimpact impacts set-status <impact_id> accepted --reason "画面/API/DBの上限値を修正対象にする"
```

`must_review` は「影響あり確定」ではなく「直接証拠と関係経路があるので必ず確認する」
という意味です。LLMだけの主張や evidence のない主張は `may_review` 以下に落とされます。

## LLM provider

LLMは標準導線です。Codex CLIを第一候補にし、OpenAI APIとOllamaも選べます。

```powershell
specimpact llm configure --provider codex --model default
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm status
specimpact llm disable
```

OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は外部送信確認が必要です。localhost Ollama と
local embeddings はローカルで動作します。CI、debug、秘匿性の強い案件では `--no-llm` を使えます。

## Obsidian Review Vault

SpecImpactのJSONLを正本にし、Obsidianは依存関係探索とレビュー用ワークベンチとして使います。

```powershell
specimpact export-obsidian .\vault
```

生成される主な内容:

- `SpecImpact/Dashboard.md`
- `SpecImpact/Artifacts/*.md`
- `SpecImpact/Evidence/*.md`
- `SpecImpact/Changes/*.md`
- `SpecImpact/Canvases/*.canvas`

Artifact note には frontmatter、Obsidianリンク、evidenceリンクが入り、標準Graph ViewやCanvasで
依存関係を確認できます。Dataview plugin を入れると未レビュー項目の一覧も表示できます。

## GUI

```powershell
python -m pip install -e ".[gui]"
specimpact gui
```

GUIは `127.0.0.1` のみに bind します。LAN公開オプションはありません。

主な画面:

- Dashboard
- Ingest / Analyze / Report
- Graph Explorer
- Dirty Excel Review Console
- Region Viewer
- Alias Review
- Impact Review Board
- Settings / Privacy

![Graph Explorer](docs/images/gui/graph-explorer.png)

GUIの詳細は [docs/gui_manual_ja.md](docs/gui_manual_ja.md) を参照してください。

## ドキュメント

- [日本語利用マニュアル](docs/user_manual_ja.md)
- [CLIリファレンス](docs/cli.md)
- [入力準備ガイド](docs/input_preparation.md)
- [構造化ローダー](docs/structured_loaders.md)
- [プライバシー](docs/privacy.md)
- [評価](docs/evaluation.md)
- [リリース手順](docs/release.md)

## 制限事項

SpecImpact は、あらゆるExcel方眼紙や図形を完全理解するツールではありません。

得意なもの:

- 画面、API、DB、外部IF、チェック仕様、テスト仕様が文書や表に書かれている設計書
- 項目名、物理名、日本語名が混在するSIer系ドキュメント
- evidence を見ながら人間がレビューできる変更影響管理

苦手なもの:

- 図形や矢印だけで意味が表現された資料
- 画像として貼られたER図
- セルの見た目だけに意味があり、文字情報がほとんどないExcel
- 大規模な実企業文書での網羅性保証

評価データは回帰テスト用です。最終的な影響正解率を保証するものではありません。

## 開発

```powershell
python -m pip install -e ".[dev,gui]"
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```

Contribution ルールは [CONTRIBUTING.md](CONTRIBUTING.md)、セキュリティ報告は
[SECURITY.md](SECURITY.md) を参照してください。
