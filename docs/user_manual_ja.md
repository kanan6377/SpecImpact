# SpecImpact 日本語ユーザーマニュアル

このマニュアルは、SpecImpact を初めて使う人が、設計書の取り込みから変更影響レビュー、Obsidian 出力まで進められるようにまとめたものです。

## 1. SpecImpact とは

SpecImpact は、設計書を Host LLM と GraphRAG で構造化し、変更依頼に対する影響候補を
evidence 付きで管理する Headless engine です。標準フロントは Cursor、同時対応hostは
Antigravityです。CLIとlocalhost Admin Consoleも削除せず利用できます。

主な対象は、SIer 現場でよくある Excel 設計書です。結合セル、複数表混在、同上、別紙参照、論理名と物理名の表記揺れを扱います。

重要な前提:

- SpecImpact の結果は影響確定ではなくレビュー候補です。
- `must_review` は「影響あり確定」ではなく「直接 evidence と graph path があるので必ず確認する」という意味です。
- LLM だけの主張や evidence のない主張は `may_review` 以下に落とされます。
- 最終判断は人間が `accepted`、`rejected`、`closed` などの status で管理します。

## 2. インストール

```powershell
git clone https://github.com/kanan6377/SpecImpact.git
cd SpecImpact
python -m pip install -e ".[mcp,gui]"
specimpact --help
```

配布版を独立toolとして入れる場合:

```powershell
uv tool install "specimpact[mcp,gui]"
# または pipx install "specimpact[mcp,gui]"
```

## 3. 最短で試す

標準のCursor経路:

```powershell
cd C:\work\my-system-impact
specimpact init
specimpact agent doctor --host cursor --project .
```

Cursorへ`plugins/cursor` MarketplaceからPluginを入れ、`/specimpact-onboard`を実行します。
取り込み後、チャットへ自然文で変更を伝えます。

```text
入会申込画面の「利用限度額」の上限を999万円から9999万円に変更したい。
画面、validation、API、DB、外部IF、境界値テストへの影響を調べて。
```

CLIだけでサンプルを確認する場合:

```powershell
specimpact onboard .\examples\dirty_sier_excel\docs `
  --no-llm `
  --aliases .\examples\dirty_sier_excel\aliases.yml

specimpact analyze .\examples\dirty_sier_excel\changes\利用限度額上限変更.md `
  --llm-first --no-llm
specimpact report --format markdown
```

## 4. LLM provider

標準導線はCursor / AntigravityのHost LLMです。SpecImpact側にprovider API keyを設定する
必要はありません。sampling対応hostではMCP sampling、非対応hostではprepare/submit Skillを使います。

```powershell
specimpact mcp --stdio --project C:\work\my-system-impact
```

Hostを使わないCLI fallbackでは、Codex CLI、OpenAI、Ollamaを設定できます。

```powershell
specimpact llm configure --provider codex --model default
specimpact llm status
```

OpenAI API:

```powershell
specimpact llm configure --provider openai --model <model>
```

Ollama:

```powershell
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
```

無効化:

```powershell
specimpact llm disable
```

外部Host、OpenAI、Codex CLI、remote Ollama、OpenAI embeddings は外部送信確認が必要です。
HostではMCP elicitation、またはlocalhost承認画面で発行した10分・1回限りGrantを使います。
localhost Ollama と local embeddings はローカルで動作します。

### Agent hostのprepare / submit

初期導入では、ingest_sourcesの完了後、Dirty Excel Regionごとに
prepare_graph_contextからsubmit_graph_extractionの順で実行します。

変更管理では、prepare_change、submit_change_atoms、prepare_impact_context、
submit_impact_hypotheses、get_change_sessionの順に進め、人間の判断後に
set_impact_decisionを実行します。

本文がwithheldの場合はapproval_urlを開きます。Hostがelicitation非対応なら、画面に出た
tokenをauthorize_prepared_contextへ1回だけ渡します。approved=trueでは代用できません。

Cursorの詳細はcursor.md、Antigravityはantigravity.mdを参照してください。

## 5. 設計書を取り込む

### Dirty Excel

```powershell
specimpact ingest-dirty-excel .\docs --aliases .\aliases.yml
```

または:

```powershell
specimpact ingest .\docs --mode dirty-excel --aliases .\aliases.yml
```

取り込み前に Excel の状態を確認できます。

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
```

Dirty Excel では、workbook、sheet、cell、region、evidence を保存します。LLM 抽出結果は Graph Proposal として保存され、承認前は確定 graph にはなりません。

### Markdown / text

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
```

### 表形式 Excel

1 行 1 レコードのような構造が明確な Excel は、従来の loader を使います。

```powershell
specimpact ingest-excel .\docs --profile sier --aliases .\aliases.yml
```

## 6. LLM 抽出と Graph Proposal

Dirty Excel region は、種類ごとに専用の LLM 指示を使います。

- `screen_item_table`
- `validation_block`
- `api_mapping_table`
- `db_mapping_table`
- `external_if_table`
- `test_case_table`

Graph Proposal を確認します。

```powershell
specimpact graph proposals list
specimpact graph proposals accept <proposal_id>
specimpact graph proposals reject <proposal_id>
```

承認した proposal だけが graph に反映されます。

## 7. Alias review

Alias 候補を生成します。

```powershell
specimpact aliases suggest --llm
specimpact aliases review
```

LLM は entity ペアごとに次の判定を返します。

| 判定 | 意味 |
| --- | --- |
| `same` | 同一概念として alias 化できる |
| `related` | 関連はあるが別概念 |
| `different` | 別概念 |
| `unsure` | 人間確認が必要 |

候補生成では、次の signal を使います。

- concept key 一致
- camelCase / snake_case 分解
- 名前トークン重複
- 疑似 embedding 類似
- 周辺 relation 類似
- 同じ evidence または近傍 evidence

確認:

```powershell
specimpact aliases confirm <candidate_id>
specimpact aliases reject-candidate <candidate_id>
```

`same` 以外を confirm しても alias としては確定しません。

## 8. 変更依頼を書く

Markdown の例:

```markdown
# 利用限度額上限変更

入会申込画面の利用限度額上限を999万円から9999万円に変更する。

API項目 requestedCreditLimit、DB項目 REQUESTED_CREDIT_LIMIT、外部IF、境界値テストも確認する。
```

Change Atom に分解:

```powershell
specimpact change parse .\changes\change_request.md
```

## 9. 変更影響分析

```powershell
specimpact analyze .\changes\change_request.md --llm-first
specimpact report --format markdown
```

自然文を直接渡す場合:

```powershell
specimpact change analyze "電話番号の桁数を10桁から11桁に変更する"
```

LLM-first impact analysis では、LLM に以下を渡します。

- Change Atom
- 候補 artifact
- candidate subgraph
- evidence quote
- 過去の accepted / rejected 判断

LLM は `impact_type`、`required_actions`、`warnings`、`uncertainty` を作業仮説として返します。ただし、LLM だけでは `must_review` に昇格できません。

## 10. Impact decision

```powershell
specimpact changes list
specimpact impacts list
specimpact impacts set-status <impact_id> accepted --reason "修正対象にする"
specimpact impacts set-status <impact_id> needs_investigation --reason "別紙参照先の確認が必要"
specimpact impacts set-status <impact_id> implemented --reason "実装完了"
specimpact impacts set-status <impact_id> tested --reason "境界値テスト完了"
specimpact impacts set-status <impact_id> closed --reason "レビュー完了"
```

Status:

- `unreviewed`
- `accepted`
- `rejected`
- `needs_investigation`
- `implemented`
- `tested`
- `closed`

## 11. Obsidian export

```powershell
specimpact export-obsidian .\vault
```

通常出力:

- `SpecImpact/Dashboard.md`
- `SpecImpact/Artifacts/*.md`
- `SpecImpact/Evidence/*.md`
- `SpecImpact/Changes/*.md`
- `SpecImpact/Impacts/*.md`
- `SpecImpact/Canvases/*.canvas`

Artifact note には relation と evidence link が入ります。Impact note には status、review priority、impact type、required actions が入ります。Canvas では変更依頼と影響候補の関係を確認できます。

旧形式の report コピー:

```powershell
specimpact export-obsidian .\vault --report-only
```

## 12. Admin Console（既存GUI）

```powershell
specimpact gui
```

`Obsidian`画面では、出力予定のnote件数とVault構成を確認し、GUIからknowledge graph exportを
実行できます。LLM transmission auditには安全なmetadataだけが表示されます。失敗した取り込み、
分析、外部送信承認、Vault出力は`ジョブと監査`画面のRecovery列を確認して再実行してください。

Admin Consoleは日常チャットの代替ではなく、設計書viewer、Graph、統一Review Queue、
Jobs/Audit、Privacy、Obsidianをまとめて確認する管理画面です。`127.0.0.1` のみに bind します。

主な画面:

- 概要
- 設計書 / Source Library
- 変更レビュー
- ナレッジグラフ
- 統一レビュー（Graph proposal / 未解決参照 / Alias / relation / Impact）
- ジョブと監査
- 設定とプライバシー

案件が未登録の場合は、GUI内で案件フォルダーを作成するか、ガイド付きサンプルを生成できます。
設計書画面はMarkdown/text、Dirty Excel、OpenAPI、DDL、CSVのmanaged uploadに対応します。設計書名を
押すと同じ画面の右ペインに内容が開きます。名前・パスによる一覧検索、本文・セル値の文書内検索、
Dirty Excelのsheet切替を利用でき、evidence対象の行またはcellは黄色で表示されます。
変更レビューは、選択した起点設計書のdocument IDと関連graph要素を分析contextへ含めます。
候補、設計書、evidenceの選択はURLへ保存され、evidenceを押すと引用元の行またはcellへ移動します。
設計書の再取り込みでhashが変わるとsource versionとgraph diffが追加され、旧evidenceに依存する
relationとImpactはstaleとして統一レビューへ戻ります。

詳細は [gui_manual_ja.md](gui_manual_ja.md) を参照してください。

## 13. evidence を確認する

```powershell
specimpact inspect evidence
specimpact inspect evidence <evidence_id>
```

Excel evidence は、workbook、sheet、cell/range、quote に戻れるように保存されます。

## 14. aliases.yml

手動 alias を書く場合:

```yaml
aliases:
  entity.application.requested_credit_limit:
    canonical_type: BusinessField
    aliases:
      - 利用限度額
      - 希望利用限度額
      - requestedCreditLimit
      - REQUESTED_CREDIT_LIMIT
```

注意:

- 同じ alias を複数 ID に割り当てないでください。
- artifact と entity の境界を無理に混ぜないでください。
- LLM alias は候補であり、確定には review が必要です。

## 15. Obsidian を使ったレビュー運用例

1. `specimpact export-obsidian .\vault`
2. Obsidian で `SpecImpact/Dashboard.md` を開く
3. Dataview で未レビュー Impact を確認する
4. Canvas で変更依頼と影響候補の関係を見る
5. CLI または GUI で impact status を更新する
6. 再度 export して note を更新する

## 16. よくあるエラー

### `specimpact` コマンドが見つからない

リポジトリルートで再インストールしてください。

```powershell
python -m pip install -e .
```

### `No analysis run exists`

先に設計書を取り込み、変更依頼を分析してください。

```powershell
specimpact ingest .\docs --aliases .\aliases.yml
specimpact analyze .\changes\change_request.md --llm-first
```

### `External transmission was not approved`

外部 LLM を使う処理で承認が不足しています。内容を確認して `--yes` を付けるか、`--no-llm` を使ってください。

### Excel がうまく読めない

まず診断してください。

```powershell
specimpact excel inspect .\docs
specimpact excel classify .\docs
```

表形式ではなく汚い Excel の場合は `ingest-dirty-excel` を使ってください。

## 17. 開発者向け確認

```powershell
python -m pip install -e ".[dev,gui]"
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check .\examples\evaluation\release_cases.yml
```

`release-check` は OSS 公開向けの品質 gate です。評価ケース数、must review recall、visible precision、evidence coverage などを確認します。
