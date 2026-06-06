# SpecImpact

SIerのExcel地獄な設計書をLLMで読解し、変更影響を証拠付きで管理する
ローカルファーストOSSです。

SpecImpact は、設計書と変更依頼を読み込み、「確認したほうがよい画面・API・DB・外部IF・
入力チェック・テスト」を根拠付きで一覧化します。出力は影響確定ではなくレビュー候補です。
最終判断は人間が行い、採否判断をローカルに蓄積します。

## 何ができるか

- Markdown、OpenAPI、DDL、CSV、表形式Excelから設計要素と関係を抽出する
- 結合セル、表記揺れ、複数表混在、別紙参照を含む汚いExcelをセル番地付きで取り込む
- 変更依頼を Change Atom に分解し、影響候補を `must_review` / `should_review` / `may_review` に分類する
- すべての候補に、ファイル名、シート名、セル番地、行番号などの evidence を残す
- alias 候補、graph 提案、impact 判断をレビューして保存する
- CLI と localhost 限定GUIのどちらでも使う

標準設定では外部サービスに設計書を送りません。

```text
LLM: disabled
External transmission: none
Backend: local JSONL
State directory: .specimpact/
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

## まず試す: Dirty Excelサンプル

日本のSIer現場でありがちな、結合セル、表記揺れ、別紙参照、同上、境界値テストを含むExcel
サンプルです。

```powershell
specimpact init
specimpact ingest-dirty-excel .\examples\dirty_sier_excel\docs `
  --aliases .\examples\dirty_sier_excel\aliases.yml
specimpact change parse .\examples\dirty_sier_excel\changes\利用限度額上限変更.md
specimpact analyze .\examples\dirty_sier_excel\changes\利用限度額上限変更.md --llm-first
specimpact impacts list
specimpact report --format markdown
```

このサンプルでは、利用限度額上限変更に対して、画面項目、API項目、チェック仕様、DB項目、
外部IF、境界値テストなどをレビュー候補として扱う流れを確認できます。

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
specimpact init
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

## 任意のLLM利用

LLMは標準で無効です。LLMを使うコマンドは、プロバイダ未設定ならローカル処理だけを実行するか、
明確なエラーメッセージを出します。

```powershell
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm configure --provider codex --model default
specimpact llm status
specimpact llm disable
```

OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は外部送信確認が必要です。
localhost Ollama と local embeddings はローカルで動作します。

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
