# Dirty SIer Excel Benchmark

SpecImpact v2 の dirty Excel 動作確認用サンプルです。日本のSIer現場でありがちなExcel設計書を、
あえて少し扱いづらい形で置いています。

含まれる要素:

- 結合セルありの画面設計
- API項目対応表の表記揺れ
- DB定義の別紙参照
- チェック仕様の同上表記
- 境界値テスト
- `利用限度額` / `requestedCreditLimit` / `REQUESTED_CREDIT_LIMIT` / `LIMIT_AMT` のalias

## 目的

最初のシナリオは、以下の変更依頼です。

```text
入会申込画面の「利用限度額」の上限を999万円から9999万円に変更する。
```

この変更に対して、SpecImpact が以下のようなレビュー対象を evidence 付きで拾えるかを確認します。

- 画面項目
- API項目
- DBカラム
- 入力チェック
- 外部IF
- 境界値テスト

## 実行手順

リポジトリルートで実行します。

```powershell
python -m pip install -e .
specimpact onboard .\examples\dirty_sier_excel\docs `
  --provider codex `
  --model default `
  --aliases .\examples\dirty_sier_excel\aliases.yml
specimpact change analyze .\examples\dirty_sier_excel\changes\利用限度額上限変更.md
specimpact impacts list
specimpact report --format markdown
specimpact export-obsidian .\vault
```

取り込みに成功すると、概ね次のような件数が表示されます。

```text
Ingested 5 workbooks, 12 regions, 7 graph proposals.
```

Codex CLIを使う場合は送信前に確認が入ります。ローカルfallbackだけで試す場合は `onboard` に
`--no-llm` を付けます。

## Excelの中身を確認する

取り込み前の状態診断:

```powershell
specimpact excel inspect .\examples\dirty_sier_excel\docs
```

sheet分類とregion検出:

```powershell
specimpact excel classify .\examples\dirty_sier_excel\docs
```

取り込み後は `.specimpact/` に以下のようなデータが保存されます。

- `sources/original/`: 元Excelの保存コピー
- normalized workbook/cell JSONL
- sheet/region分類
- graph proposals
- evidence records
- impact decisions

## 提案をレビューする

Graph proposal:

```powershell
specimpact graph proposals list
specimpact graph proposals accept <proposal_id>
specimpact graph proposals reject <proposal_id>
```

Alias candidate:

```powershell
specimpact aliases suggest
specimpact aliases review
specimpact aliases confirm <candidate_id>
specimpact aliases reject-candidate <candidate_id>
```

Impact decision:

```powershell
specimpact impacts list
specimpact impacts set-status <impact_id> accepted --reason "上限値変更の修正対象"
specimpact impacts set-status <impact_id> needs_investigation --reason "別紙参照先の確認が必要"
```

## Obsidianで見る

```powershell
specimpact export-obsidian .\vault
```

`.\vault` をObsidianで開くと、`SpecImpact/Dashboard.md`、artifact note、evidence note、
変更単位の `.canvas` を確認できます。SpecImpactのJSONLが正本で、Obsidianはレビュー用の
探索ワークベンチです。

## ほかの変更シナリオ

同じExcel群に対して、以下の変更依頼も用意しています。

```powershell
specimpact change analyze .\examples\dirty_sier_excel\changes\電話番号桁数変更.md

specimpact change analyze .\examples\dirty_sier_excel\changes\本人確認方式変更.md
```

## 期待結果ファイル

`goldens/利用限度額上限変更.expected.json` は回帰テスト用の期待結果です。
通常利用では直接編集する必要はありません。
