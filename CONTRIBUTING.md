# Contributing

SpecImpact は、設計変更の影響候補を evidence 付きでレビューするためのローカルファースト
OSSです。新しい抽出ロジックやLLM連携を追加する場合は、「便利そう」よりも
「根拠を追える」「誤検知をレビューできる」「外部送信を制御できる」を優先してください。

## 開発環境

```powershell
git clone https://github.com/kanan6377/SpecImpact.git
cd SpecImpact
python -m pip install -e ".[dev,gui,mcp]"
specimpact --help
```

## 変更前に確認すること

- 既存のv1 CLI、schema、report、GUI、local JSONL backendを壊さない
- LLM出力は確定結果ではなく、review可能なproposalまたはhypothesisとして扱う
- evidence のない抽出結果を `must_review` にしない
- 外部送信はpreviewと有効なGrantなしで実行しない
- MCP Resourceからsource bodyやEvidence quoteを直接返さない
- Host chat、Canvas、ArtifactをJSONLのsource of truthにしない
- テストで外部プロバイダを呼ばない

## テスト

PR前に以下を実行してください。

```powershell
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```

GUIやdirty Excelを変更した場合は、該当テストも追加・更新してください。

## テスト追加の目安

- 新しい抽出ルール: parser test、evidence ID test、評価case
- dirty Excel: workbook/cell/region/evidence の往復確認
- LLM連携: fake provider を使い、schema validation と evidence validation を確認
- alias推論: confirm/reject の永続化を確認
- impact管理: Change Atom、impact decision、status更新を確認
- GUI: API/service test と既存画面の回帰確認
- MCP: schema、unknown ID、pagination、workspace escape、idempotencyを確認
- Host LLM: Fake sampling/prepare-submitでschema違反とverifier downgradeを確認
- Plugin: manifest、Skills、Rules、Hooks、Canvas/Artifactをsnapshot確認

## Issue / PR の書き方

Issue には以下を書いてください。

- 入力文書の種類: Markdown、clean Excel、dirty Excel、OpenAPI、DDL、CSV
- 期待したレビュー候補
- 実際に出たレビュー候補
- evidence が不足している箇所
- 外部LLMを使ったかどうか

PR には以下を書いてください。

- 変更概要
- 追加・更新したテスト
- 互換性への影響
- 外部送信やprivacy設定への影響

機密の設計書、認証情報、APIキーはIssueやPRに含めないでください。
