# SpecImpact 改善提案サイト — 広報・GUI/UX・実装プラン

[SpecImpact](https://github.com/kanan6377/SpecImpact)(SIerの汚いExcel設計書をLLM+GraphRAGで evidence 付き変更影響レビューに変えるOSS)を、**アイディアはそのままに、スターが集まるOSSへ育てる**ための改善提案パッケージです。

## プロジェクトの目的

1. **GUI/UXのリデザイン提案** — 実際に触れるインタラクティブ・プロトタイプとして提示(実装の設計図としてそのまま使える)
2. **広報戦略** — 「共感 → 体験 → 拡散」の4本柱と、週次タスクまで落とした90日プレイブック
3. **実装改善バックログ** — スター獲得に直結する順(P0〜P2)で整理

## エントリーポイント(機能URI)

| パス | 内容 |
|---|---|
| `index.html` | 提案トップ:現状診断 / GUIリデザインの考え方 / 広報4本柱 / 実装バックログ(新GUIのiframe埋め込みあり) |
| `console.html` | **GUIリデザイン・プロトタイプ**(完全クライアントサイド・合成データで動作) |
| `strategy.html` | 90日成長プレイブック:週次タスク / READMEテンプレート / X・Show HN投稿ドラフト / KPI |
| `preview-patched.html` | **本体適用用パッチの検証ハーネス**：実際の SpecImpact GUI(app.js/app.css)を fetch モックでローカル再現。`?page=graph` / `?page=analyze` 等でページ切替 |

## 本体リポジトリへの適用(patched/)

GitHub の実ファイル(`specimpact/webui/` 配下)を取得し、リデザインを適用したコピーバック可能なファイル一式を `patched/` に用意しました。

- 変更は **app.css(全面リデザイン) / app.js(4箇所) / index.html(nav見出し追加)** の3ファイルのみ
- **クラス名・ID・DOM構造・Python コードは無変更**(既存テスト `tests/test_gui.py` を壊さない)
- **外部 CDN/フォント追加なし**(local-first の思想を守る)
- 適用手順・commit メッセージ案・検証済み項目は [`patched/APPLY.md`](patched/APPLY.md) を参照

## 完成済み機能

### console.html(新GUIプロトタイプ)
- **ダッシュボード**:統計カード + 「次にやること」ステップ導線 + Project Pulse + 影響候補内訳ドーナツチャート(Chart.js)
- **影響レビューボード**:must/should/may の優先度カラー付きカード。展開すると graph path・evidence引用(ファイル+セル範囲+引用文)・required actions・LLM作業仮説(confidence bar)を表示。検索・優先度フィルタ・status更新(accepted/closed/dismissed)が動作
- **Graph Explorer**:D3.js force layout。ノード衝突回避・ラベル白フチで可読性確保。「影響パス強調」ボタン、ノード検索、ノード選択で右パネルに relation+evidence 表示、confirm/reject のその場更新
- **Alias レビュー**:利用限度額 ↔ requestedCreditLimit 等の表記揺れ候補を LLM判定(same/unsure/different)+ evidence + シグナル付きでレビュー・確定/却下
- **ジョブ履歴**:外部送信の承認状態を可視化したテーブル
- ナビの未処理バッジ、トースト通知、Privacy Doctor 常設カード

### デモシナリオ(合成データ)
「入会申込画面の利用限度額上限を999万円→9999万円に変更する」という変更要求が、画面 → 入力チェック → API → DB(NUMBER(7)桁あふれ)→ 外部IF(固定長)→ テスト → バッチへ波及する様子を再現。

## データモデル / ストレージ

- すべて `js/data.js` 内の静的モックデータ(合成データ)。バックエンド・Table API は不使用
- 構造は SpecImpact 本体の概念(impacts, graph nodes/links, aliases, jobs, change atoms)に準拠しており、本体の JSONL をそのまま流し込める形を意識

## ファイル構成

```
index.html        提案トップ(Tailwind CDN)
console.html      新GUIプロトタイプ
strategy.html     90日プレイブック
css/console.css   コンソール用デザイントークン&スタイル
js/data.js        合成デモデータ
js/console.js     コンソールのロジック(D3グラフ・Chart.js・レビュー操作)
preview-patched.html    パッチ検証ハーネス(実 app.js/app.css + fetch モック)
patched/                ★ SpecImpact 本体へコピーするパッチ済み実ファイル
  APPLY.md              適用手順・変更点・commit メッセージ案
  specimpact/webui/static/app.css        全面リデザイン(ドロップイン置換)
  specimpact/webui/static/app.js         4箇所のスタイル修正
  specimpact/webui/templates/index.html  nav セクション見出し追加
  *.orig                GitHub main の変更前ファイル(diff 確認用)
_research/        元リポジトリの調査メモ・検証スクリプト
```

## 未実装 / 今後の推奨ステップ

- プロトタイプは表示・操作のみで永続化なし(本実装ではSpecImpactのローカルAPIに接続)
- GUI の i18n(日英切替)モック
- HTMLレポート出力のサンプルページ(`report.html`)— 「上司にそのまま送れる」訴求のデモ用
- デモGIF録画(console.html を素材に)

## デプロイ

公開するには **Publish タブ** からワンクリックでデプロイできます。
