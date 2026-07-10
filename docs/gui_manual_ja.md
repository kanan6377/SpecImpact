# SpecImpact GUI Manual

SpecImpact GUIは、設計変更の影響候補、設計書、relation path、evidenceを一つの案件文脈で
確認するlocalhost専用のEvidence Review Workspaceです。LLMの出力は確定判断ではなく、
人間が根拠を確認するためのproposalまたはhypothesisとして扱います。

## 1. 起動

```powershell
python -m pip install -e ".[gui]"
specimpact gui
```

既定URLは `http://127.0.0.1:8765/ui/dashboard` です。GUIは常に `127.0.0.1` にbindし、
LAN公開optionはありません。

```powershell
specimpact gui --port 8765
specimpact gui --project C:\work\my-system-impact
specimpact gui --no-open-browser
```

## 2. 画面構成

左sidebarは案件内の作業領域、上部barは案件選択とprovider/privacy状態です。URLは画面ごとに
保持され、`project_id` queryで選択中の案件を維持します。

| 画面 | 用途 |
| --- | --- |
| 概要 | documents、artifacts、entities、relations、evidence、次のレビューを確認 |
| 設計書 | 原本をmanaged uploadし、evidence graphへの取り込み状態を確認 |
| 変更レビュー | 変更要求の入力、影響候補、設計書、evidenceを並べてレビュー |
| ナレッジグラフ | node/relationの接続とpropertyを探索 |
| レビュー | Graph proposal、未解決参照、Alias、relation、Impactを判断 |
| ジョブと監査 | 案件queueの処理状態と安全な入力要約を確認 |
| 設定 | LLM provider、保存先、外部送信状態、Privacy Doctorを確認 |

## 3. 案件作成と設計書

案件が一件もない場合、GUIに初期導入画面が表示されます。案件名とローカルフォルダーを入力して
`案件を開始` を押すと、フォルダー作成、registry登録、`.specimpact` 初期化を行います。実データを
使わずに確認する場合は `ガイド付きサンプルを作成` を選びます。

`設計書` 画面では種類を選び、ファイルを追加します。

| 種類 | 拡張子 | 取り込み |
| --- | --- | --- |
| 文書 | `.md`, `.txt` | LLM-first document ingestion |
| Dirty Excel | `.xlsx` | cell/region正規化とLLM proposal抽出 |
| OpenAPI | `.yaml`, `.yml`, `.json` | structured OpenAPI loader |
| DDL | `.sql` | structured DDL loader |
| CSV | `.csv` | table loader |

原本は `.specimpact/uploads/<timestamp>-<uuid>/` へ保存し、元ファイルを上書きしません。1ファイルは
25 MB、1回の送信は200ファイルまでです。外部LLMを使う設定では取り込み前に送信内容をpreviewし、
承認後もserverとcoreの両方で承認を検証します。

Source Libraryは現在のdocumentごとにstatus、evidence、artifact、relation、Dirty Excelのsheet数、
warningを表示します。`indexed` は文書として登録済みだがrelation evidenceがない状態、`ready` は
evidenceを持つ状態です。`Version` は同じdocument IDで観測したhash世代数です。再取り込みでhashが
変わると、その文書に依存する未解決stale件数を赤いstatusとwarning数で表示します。

## 4. 変更レビュー

1. 上部barで案件を選ぶ
2. `変更レビュー` を開く
3. `起点となる設計書` を選ぶ。案件全体を対象にする場合は `案件全体` を選ぶ
4. `変更内容` に自然文を入力する
5. `影響分析` を実行する
6. 左の候補、中央の設計書、右のEvidence Inspectorを照合する

起点設計書を選ぶと、ファイルパスだけでなくdocument ID、タイトル、その文書由来のartifact/entityを
Graph Contextとして変更要求へ追加します。これは分析対象を選択文書だけへ狭めるfilterではなく、
GraphRAGが変更要求を解釈する起点です。案件全体の依存関係は引き続き探索します。

候補を選ぶと、関連する設計書へ切り替えられます。該当行またはExcel cellは黄色で
ハイライトされ、Excel検索結果のように変更確認箇所を追えます。Inspectorには以下を表示します。

- `review_priority` と `evidence_strength`
- local ruleによるreason
- relation path
- LLMが提案したrequired actions
- evidence ID、元ファイル、行番号またはcell、quote

Inspectorのevidenceを選ぶと、中央paneが該当設計書へ切り替わり、引用元の行またはcellをfocus表示します。
候補、設計書、evidence IDはURLの `impact`、`source`、`evidence` queryへ保存されるため、再読み込みや
URL共有で同じレビュー位置へ戻れます。Verifier欄ではmatch type、rule assessment、relation distance、
relation statusを確認できます。

`must_review` は影響確定ではなく、直接evidenceとgraph pathがあるため必ず確認すべき候補です。
Inspectorは狭幅画面ではoverlayになり、右上の閉じるbuttonで設計書へ戻れます。

## 5. ナレッジグラフ

GraphはCytoscapeで描画します。検索欄にartifact/entity名を入力すると非該当nodeを弱く表示します。
nodeまたはrelationを選択すると右Inspectorへpropertyを表示します。Graphは因果関係の確定図ではなく、
設計書から抽出してreview statusを持つ依存関係です。

## 6. 統一Review Queue、ジョブ、設定

`レビュー` 画面は次の判断対象を一つのqueueへまとめます。

- Graph proposal: 追加予定node/edgeとevidenceを見てaccept/reject
- 未解決参照: `別紙参照`、`同上` などを要調査として表示
- Alias: LLM judgement、周辺relation、evidenceを見てconfirm/reject
- Relation: source/target、抽出方法、polarity、evidenceを見てconfirmed/unconfirmed/rejected
- Impact: statusと判断理由を保存
- Graph diff: 再取り込みtransactionで追加・削除・変更されたrelationをreviewed/ignoredにする

種類と状態でfilterできます。選択項目は `review` queryへ保存されます。判断更新はブラウザ内だけで
先行反映せず、案件queueでcore serviceを実行し、永続化に成功してから全データを再読込します。
Impact statusは `unreviewed / accepted / rejected / needs_investigation / implemented / tested / closed`
を使用します。

source hashが変わると、変更前evidenceに依存するnode、relation、Impactを `stale` として要確認へ
戻します。既存confirmed relationも `unconfirmed` に戻り、relationまたはImpactを再判断すると
対応するstale recordが解消されます。Graph Explorerはstale node/edgeを赤い枠または破線で表示します。

履歴は追加collectionへ保存します。

```text
.specimpact/source_versions.jsonl
.specimpact/graph_diffs.jsonl
.specimpact/stale_records.jsonl
```

ジョブと監査画面は案件ごとのqueueを表示します。文書本文、API key、providerのraw responseは
job履歴へ保存しません。失敗時はstatusと安全な入力要約から復旧箇所を確認します。

設定画面ではprovider/model、local fallback、backend、案件path、最新run、Privacy Doctorを確認します。
外部LLM送信はpreviewとjob単位の承認が必要で、core側でも再検証します。

### Obsidianと送信監査

`Obsidian`画面は、ローカルJSONL graphをレビュー用Vaultへ変換します。出力前にArtifact、
Evidence、Impact、Canvasの予定件数と生成ディレクトリを確認できます。`Vaultへ出力`は案件の
job queueを通り、`Dashboard.md`、Artifact / Evidence / Change / Impact note、Canvasを生成します。

同画面のLLM transmission auditは、provider、model、purpose、item count、redaction有無、
source/prompt/response hashだけを表示します。prompt本文、設計書本文、evidence quote、
raw response、API keyはAPIのallowlistにも含めません。Latest review replayはrun、change、
retrieval、impact件数を表示し、分析を追跡できるようにします。

`ジョブと監査`画面でfailed jobを確認すると、外部送信承認、入力ファイル、LLM設定、Vaultの
書き込み権限など、actionに応じた復旧手順が表示されます。

## 7. URL互換性

現行URL:

```text
/ui/dashboard
/ui/sources
/ui/impact-board
/ui/graph
/ui/reviews
/ui/vault
/ui/jobs
/ui/settings
```

旧URLは案件IDを保持してredirectします。

```text
/ui/demo -> /ui/dashboard
/ui/ingest, /ui/dirty-excel -> /ui/sources
/ui/analyze -> /ui/impact-board
/ui/aliases -> /ui/reviews
/ui/tools -> /ui/jobs
```

## 8. Frontend開発

アクセシビリティ契約:

- 最初のTab移動でskip linkからmainへ移動できる
- icon-only buttonにはaccessible nameがある
- 外部送信確認はnative dialogで開き、キャンセルを初期focusにする
- Graphはcanvasだけに依存せず、選択欄からキーボードでもnode/relationをInspectorへ表示できる
- 狭幅の変更レビューは候補一覧から始まり、候補選択後にInspectorを開く
- `prefers-reduced-motion`ではloop/transition時間を最小化する

Cytoscapeはdynamic importされます。DashboardなどGraph以外の初期表示ではgraph chunkを取得せず、
Graph画面を開いた時だけ読み込みます。production HTMLはlocalhost用のため検索indexを禁止します。

利用者はNode.jsを必要としません。`specimpact/webui/static/dist/` のbuild済み資産をPython packageに
同梱します。GUIを変更する開発者だけが次を実行します。

```powershell
cd frontend
npm install
npm run check
npm run build
cd ..
pytest -q tests/test_gui.py
```

runtime CDN、remote font、mock data fallbackは使用しません。FastAPIが既存のlocal JSONL project modelと
CSRF/session保護されたAPIを提供し、React/TypeScript frontendがそれを表示します。

## 9. 安全性と制約

- 最終的な影響判断は人間が行う
- LLMだけの主張を `must_review` にしない
- 設計書を自動編集しない
- 外部送信は明示設定と承認が必要
- API keyと文書本文をjob logへ残さない
- Graphの更新は案件queueと永続化serviceを経由する

source version、graph diff、stale dependencyは実装済みです。Source Libraryでversion、
Graphでstale node/relation、統一Review Queueで再レビュー対象を確認できます。
設計判断と完了記録は [UX Redesign Plan](ux_redesign_plan.md) と
[Phase Status](phase_status.md) を参照してください。
