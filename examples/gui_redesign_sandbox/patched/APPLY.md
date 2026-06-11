# SpecImpact 本体への適用手順

このディレクトリには、SpecImpact リポジトリの **実ファイルに対するパッチ適用済みコード**が入っています。
`*.orig` は GitHub の `main` ブランチから取得した元ファイル(変更前)で、diff 確認用です。

## 変更ファイル(3ファイルのみ)

| リポジトリ内パス | 変更内容 |
|---|---|
| `specimpact/webui/static/app.css` | **全面リデザイン**(セレクタ・クラス名は全て維持したドロップイン置換) |
| `specimpact/webui/static/app.js` | 4箇所の小修正(後述) |
| `specimpact/webui/templates/index.html` | サイドバーにセクション見出し3つを追加(既存要素は無変更) |

Python コード・API・テスト対象のロジックには一切触れていません。

## 適用コマンド

```bash
cd SpecImpact

# このプロジェクトの patched/ ディレクトリの中身をコピー(.orig は除く)
cp <このサイト>/patched/specimpact/webui/static/app.css    specimpact/webui/static/app.css
cp <このサイト>/patched/specimpact/webui/static/app.js     specimpact/webui/static/app.js
cp <このサイト>/patched/specimpact/webui/templates/index.html specimpact/webui/templates/index.html

# 検証
pytest -q
ruff check .
specimpact gui   # 目視確認

git checkout -b redesign/console-ux
git add specimpact/webui
git commit -m "feat(gui): redesign console UX

- Unify semantic colors: must=red / should=amber / may=blue,
  confirmed=green / unconfirmed=amber / rejected=gray
- Color-code report priority sections (priority-<group> classes)
- Style evidence as quote cards (accent left border)
- Distinguish unconfirmed edges (amber dashed) in Graph Explorer
- Group sidebar nav into はじめる / ワークフロー / 運用
- Refresh design tokens (indigo accent, lighter sidebar, soft shadows)"
git push origin redesign/console-ux
```

## app.js の変更点(4箇所・全て描画スタイルのみ)

1. **`loadReport()`**: priority セクションに `priority-${group}` クラスを追加
   → CSS で must/should/may/hidden を色分け表示できるように
2. **node 既定色**: `#2563eb` → `#4f46e5`(アクセント色をコンソール全体と統一)
3. **entity 色**: `#0f766e` → `#0891b2`(凡例と一致)
4. **edge スタイル**: `unconfirmed`(琥珀・破線)を新設、`rejected` を赤→灰破線に変更
   → 「rejected=危険」ではなく「rejected=無効化済み」という意味論に合わせ、
     未確認(レビュー待ち)こそ注意を引く配色に

## index.html の変更点(1箇所)

サイドバー nav に `<span class="nav-label">` を3つ追加(はじめる / ワークフロー / 運用)。
既存のリンク・`data-nav` 属性・URL は一切変更していないため、
`PAGES` 定義や `tests/test_gui.py` には影響しません。

## 検証済み事項(このプロジェクト内で確認)

`preview-patched.html` が FastAPI バックエンドを fetch モックで代替し、
パッチ済みの実 `app.js` / `app.css` を実際に実行して検証しています:

- ✅ dashboard / analyze / impact-board / graph / aliases / dirty-excel / jobs 全ページ描画
- ✅ レポートの priority 色分け(4セクション)
- ✅ Graph Explorer: cytoscape 描画・relation テーブル4行・ノード選択で evidence 表示
- ✅ Impact Board: decision テーブル・must_review ピルの色
- ✅ Aliases: judgement グループ(same/unsure)・confirm ボタンの disabled 制御
- ✅ Jobs: failed job の recovery hint 表示
- ✅ コンソールエラーなし

## 設計上の制約(意図的に守ったこと)

- **クラス名・ID・DOM構造を維持** → `app.js` の既存セレクタと `tests/test_gui.py` を壊さない
- **外部フォント・CDN を追加しない** → local-first / オフライン動作の思想を守る
  (`Inter` / `JetBrains Mono` は font-family の候補として記述、未インストール環境では既存フォントにフォールバック)
- **Python 側は無変更** → レビュー範囲を webui の静的アセットに限定
