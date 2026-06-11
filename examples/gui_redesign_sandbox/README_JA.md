# GUI Redesign Sandbox

このディレクトリは、`code_sandbox_light_git_49163440_1781154161.zip` の内容を丸ごと取り込んだ保存領域です。

## 位置づけ

- `patched/specimpact/webui/` の3ファイルは、すでに本番GUIへ適用済みです。
  - `specimpact/webui/static/app.css`
  - `specimpact/webui/static/app.js`
  - `specimpact/webui/templates/index.html`
- それ以外のファイルは、検証用ハーネス、調査メモ、standaloneプロトタイプ、差分確認用の原本です。
- 本番の `specimpact` パッケージには読み込まれません。
- 一部のHTMLはCDNやモックデータを使うsandboxです。SpecImpact本体のlocal-first実装とは切り離して扱います。

## 主なファイル

- `preview-patched.html`
  - 実際の `app.js` / `app.css` をfetchモックで動かす検証ハーネスです。
- `console.html`
  - GUI redesign prototypeです。
- `index.html`
  - 提案・説明用トップページです。
- `strategy.html`
  - 広報・運用・成長戦略のプレイブック案です。
- `css/console.css`
  - standalone prototype用CSSです。
- `js/console.js`
  - standalone prototype用ロジックです。
- `js/data.js`
  - standalone prototype用モックデータです。
- `patched/`
  - 本番リポジトリへ適用するためのパッチ済みファイルと `.orig` 差分確認用ファイルです。
- `_research/`
  - GitHub API取得結果、調査用HTML、参考テストなどの作業資料です。

## 注意

このディレクトリは成果物の保存と参照が目的です。CIやlintの対象にはしていません。production GUIの実装は `specimpact/webui/` を確認してください。
