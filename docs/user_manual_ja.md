# SpecImpact 利用マニュアル

ローカル GUI を利用する場合は [GUI マニュアル](gui_manual_ja.md) を参照してください。

## 1. SpecImpact とは

SpecImpact は、設計書と変更依頼を読み込み、影響を確認したほうがよい対象と根拠を一覧化する
CLI ツールです。

SpecImpact は影響範囲を自動決定しません。出力はレビュー候補です。最終判断は設計者、
開発者、テスト担当者が行ってください。

標準設定では外部サービスへ設計書を送信しません。解析データは作業ディレクトリの
`.specimpact/` に保存されます。

## 2. 動作環境

- Python 3.11 以上
- PowerShell またはコマンドプロンプト
- SpecImpact のソースコード:
  `C:\Users\kanan3525\SpecImpact`

以下の例は PowerShell 用です。

## 3. 初回セットアップ

PowerShell を開き、SpecImpact のディレクトリへ移動します。

```powershell
cd C:\Users\kanan3525\SpecImpact
python -m pip install -e .
```

インストールを確認します。

```powershell
specimpact --help
```

`specimpact` コマンドが見つからない場合は、代わりに `python -m specimpact` を使用できます。

```powershell
python -m specimpact --help
```

## 4. まずサンプルを動かす

最初に同梱サンプルで一連の操作を確認します。

```powershell
cd C:\Users\kanan3525\SpecImpact
specimpact init
specimpact ingest .\examples\credit_card_enrollment\docs `
  --aliases .\examples\credit_card_enrollment\aliases.yml
specimpact analyze .\examples\credit_card_enrollment\changes\change_credit_limit.md
specimpact report --format markdown
specimpact why "カード入会申込API"
```

実行後、作業ディレクトリに `.specimpact/` が作成されます。

## 5. 自分の設計書を解析する

### 5.1 作業ディレクトリを作る

プロジェクトごとに作業ディレクトリを分けてください。`.specimpact/` は現在の
ディレクトリに作られます。

```powershell
mkdir C:\work\my-system-impact
cd C:\work\my-system-impact
mkdir docs
mkdir changes
```

`docs\` に Markdown またはテキスト形式の設計書を配置します。

### 5.2 初期化する

```powershell
specimpact init
```

### 5.3 設計書を読み込む

alias ファイルをまだ作っていない場合:

```powershell
specimpact ingest .\docs
```

alias ファイルを用意した場合:

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
```

設計書を更新した後は、同じコマンドで再読み込みしてください。削除した Markdown 文書は
ローカルグラフから除去されます。

### 5.4 変更依頼を作る

`changes\change_example.md` を作成します。先頭に Markdown 見出しが必要です。

```markdown
# 変更依頼: 利用上限の変更

## 変更内容

requestedCreditLimit の上限を変更する。

## 確認したい観点

- API リクエスト
- 入力チェック
- DB カラム
- 外部連携
```

### 5.5 解析する

```powershell
specimpact analyze .\changes\change_example.md
```

### 5.6 レポートを見る

人が読む Markdown レポート:

```powershell
specimpact report --format markdown
```

ツール連携や詳細確認に使う JSON レポート:

```powershell
specimpact report --format json
```

Markdown レポートには `must_review` と `should_review` が表示されます。JSON レポートには
`may_review` と `hidden` も含まれます。

## 6. レポートの読み方

主な項目は以下です。

| 項目 | 意味 |
| --- | --- |
| `artifact_id` | ツール内部で使う安定 ID |
| `display_name` | 人が読む表示名 |
| `review_priority` | レビュー優先度 |
| `evidence_strength` | 証拠の明示度 |
| `match_type` | 完全一致、alias、一部推論などの一致方法 |
| `relation_distance` | 変更対象から候補までの関係距離 |
| `reason` | 候補に挙がった理由 |
| `relation_paths` | 変更対象から候補までの経路 |
| `evidence_ids` | 根拠レコードの ID |
| `needs_review` | 人による確認が必要か |

`review_priority` の意味:

| 値 | 意味 |
| --- | --- |
| `must_review` | 直接関係や明示的な証拠があり、優先して確認する |
| `should_review` | 関係が近く、確認したほうがよい |
| `may_review` | 弱い一致や言及のみで、必要に応じて確認する |
| `hidden` | 証拠が弱い。Markdown には表示されない |

`evidence_strength` は確率ではありません。SpecImpact は未較正の confidence score を
出力しません。

## 7. なぜ候補に入ったか確認する

表示名、alias、または内部 ID を指定できます。

```powershell
specimpact why "カード入会申込API"
specimpact why api.card_application.submit
```

候補に入らなかった理由を trace から確認する場合:

```powershell
specimpact why-not "本人確認サービス"
```

## 8. 設計書の推奨 Markdown 形式

SpecImpact は見出しと箇条書きを使った、確認しやすい Markdown を解析します。

### 8.1 API

```markdown
# API: Payment Submit API

## Request fields
- paymentAmount
- merchantId

## Response fields
- paymentId
- paymentStatus

## Calls
- Fraud Gateway
```

### 8.2 画面

```markdown
# Screen: Payment Entry Screen

## Fields
- paymentAmount
- merchantId

## Calls
- Payment Submit API
```

### 8.3 テーブル

```markdown
# Table: PAYMENT

- payment_id
- payment_amount
- payment_status
```

テーブルの column は `Table:` 見出しの直下へ箇条書きしてください。

### 8.4 外部 IF

```markdown
# ExternalIF: Fraud Gateway

## Sends
- paymentAmount
- merchantId

## Receives
- fraudRiskScore
```

使用できる代表的な artifact:

- `API`
- `Screen`
- `Table`
- `Column`
- `ValidationRule`
- `ExternalIF`
- `TestCase`
- `Batch`
- `Document`

使用できる代表的な関係見出し:

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

## 9. alias を設定する

表記揺れがある場合は `aliases.yml` を用意します。

```yaml
aliases:
  api.payment.submit:
    canonical_type: API
    aliases:
      - Payment Submit API
      - 決済登録API

  entity.payment.amount:
    canonical_type: BusinessField
    aliases:
      - paymentAmount
      - payment_amount
      - 決済金額
```

注意:

- alias は別の内部 ID と重複させないでください。
- 型が異なる artifact 間でも同じ alias は使用できません。
- `canonical_type` は `API`、`Table`、`BusinessField` などの許可された型を指定します。
- aliases は文字列の配列で指定します。

読み込み済み graph に alias を追加する場合:

```powershell
specimpact aliases add api.payment.submit payment-submit
specimpact aliases list
specimpact aliases remove api.payment.submit payment-submit
```

候補を生成して確認する場合:

```powershell
specimpact aliases suggest
specimpact aliases list
specimpact aliases approve api.payment.submit payment-submit
specimpact aliases reject api.payment.submit unused-alias
```

## 10. graph と証拠を確認する

graph の関係一覧:

```powershell
specimpact inspect graph
```

artifact の詳細:

```powershell
specimpact inspect artifact api.payment.submit
```

証拠一覧:

```powershell
specimpact inspect evidence
```

証拠 ID を指定:

```powershell
specimpact inspect evidence ev.example
```

抽出された relation の状態を確認:

```powershell
specimpact relations list
```

relation を確認済みにする:

```powershell
specimpact relations set-status rel.example confirmed
```

relation を候補生成から除外する:

```powershell
specimpact relations set-status rel.example rejected
```

状態として `confirmed`、`unconfirmed`、`rejected` を指定できます。

## 11. 構造化ファイルを読み込む

Markdown に加えて、以下のファイルを読み込めます。

OpenAPI YAML または JSON:

```powershell
specimpact ingest-openapi .\openapi.yml
```

SQL DDL:

```powershell
specimpact ingest-ddl .\schema.sql
```

CSV:

```powershell
specimpact ingest-csv .\fields.csv
```

Excel:

```powershell
specimpact ingest-excel .\fields.xlsx
```

制約:

- OpenAPI は通常の mapping 構造を持つ YAML または JSON を使用してください。
- SQL DDL は単純な `CREATE TABLE` を対象にしています。
- CSV と Excel は 1 行目をヘッダーとして扱います。
- Excel は単純な表形式を対象にしています。結合セルや自由レイアウトには対応していません。
- 個別 ingest では、別ディレクトリに同名ファイルを置くと document ID が衝突します。
  ファイル名を変更してから読み込んでください。

## 12. 状態とプライバシーを確認する

現在の状態:

```powershell
specimpact status
```

プライバシー設定:

```powershell
specimpact doctor --privacy
```

標準利用では backend が `local` であることを確認してください。

## 13. データをリセットする

解析状態は作業ディレクトリの `.specimpact/` に保存されています。

最初からやり直す場合は、必要に応じて `.specimpact/` をバックアップした後、作業
ディレクトリ内の `.specimpact/` を削除して `specimpact init` から再実行してください。

削除対象が正しい作業ディレクトリ内であることを必ず確認してください。

## 14. よくあるエラー

### `specimpact` コマンドが見つからない

以下を実行してください。

```powershell
cd C:\Users\kanan3525\SpecImpact
python -m pip install -e .
```

または `specimpact` の代わりに `python -m specimpact` を使用してください。

### `No analysis run exists`

先に設計書を読み込み、変更依頼を解析してください。

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
specimpact analyze .\changes\change_example.md
```

### `Document ID collision`

別ディレクトリに同名の structured、CSV、Excel ファイルがあります。ファイル名を変更して
から再度読み込んでください。

### `Ambiguous alias`

同じ alias が複数の内部 ID に割り当てられています。`aliases.yml` の重複を解消して
ください。

### `Invalid OpenAPI source`

OpenAPI の `paths`、path item、operation、`responses` などが mapping 形式になっているか
確認してください。

### `Invalid Excel source`

拡張子だけでなく、ファイルが有効な `.xlsx` workbook であることを確認してください。

## 15. 補助機能

Obsidian 用 Markdown export:

```powershell
specimpact export-obsidian .\vault
```

graph baseline の作成と比較:

```powershell
specimpact baseline create before
specimpact graph diff before
```

レビュー結果 JSON の import:

```powershell
specimpact review import .\review-results.json
```

Neo4j backend は任意機能です。通常利用では local backend のまま使用してください。

## 16. 開発者向けコマンド

以下は通常利用では不要です。

```powershell
pytest
ruff check .
specimpact release-check .\examples\evaluation\release_cases.yml
```

`release-check` は OSS 公開用の品質 gate です。通常の変更影響レビューでは実行不要です。
