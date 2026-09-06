# SpecImpact MCP / Agent Host Guide

## Position

MCP is a transport over the same `specimpact.application.ApplicationService` used by the Admin
Console. It does not introduce a second graph or decision store. `.specimpact/*.jsonl` remains the
source of truth.

Install and start one stdio server per workspace:

```powershell
python -m pip install -e ".[mcp]"
specimpact mcp --stdio --project C:\work\my-system-impact
```

Run `specimpact init` in the project before using operational tools. An uninitialized server only
returns onboarding data from its project resource; it does not expose source bodies.

## Codex CLI / Desktop

Codexからも同じstdio MCP serverを利用できます。外部Hostとして扱い、本文送信前のPreviewと
一回限りGrantを必須にする登録例です。

```powershell
codex mcp add specimpact `
  --env SPECIMPACT_HOST=codex `
  --env SPECIMPACT_HOST_EXTERNAL=true `
  -- specimpact mcp --stdio --project C:\work\my-system-impact

codex mcp list
```

Codex CLI、Desktop、IDE extensionは同じCodex MCP設定を参照します。登録後はCodexへ
「SpecImpact MCPを使って設計書を取り込み、この変更の影響候補をEvidence付きで調べて」と
自然文で依頼できます。SpecImpact側の正式状態は`.specimpact/*.jsonl`に保存され、Codexの応答
だけで`must_review`や人間の決定を確定しません。

## Tools

| Tool | Purpose |
| --- | --- |
| `ingest_sources` | Start local-only design-source ingestion |
| `prepare_graph_context` / `submit_graph_extraction` | Host LLM Dirty Excel region round trip |
| `prepare_change` / `submit_change_atoms` | Host LLM Change Atom round trip |
| `prepare_impact_context` / `submit_impact_hypotheses` | Host LLM impact round trip |
| `get_change_session` | Read Change Atoms and decisions for one change |
| `set_impact_decision` | Persist a human review status |
| `resolve_alias` | Confirm or reject an Alias Candidate |
| `decide_graph_proposal` | Accept or reject a Graph Proposal |
| `open_evidence` | Read authoritative Evidence and an Admin Console deep link |
| `export_obsidian` | Start a workspace-contained Vault export |
| `get_job` / `list_jobs` / `cancel_job` | Track durable local jobs |

No generic `execute(action, params)` tool is exposed. Mutation tools require an idempotency key.
Keys are stored only as SHA-256 hashes.

## Resources And Prompts

Resources use `specimpact://projects`, `sources`, `evidence`, `changes`, `impacts`, and `graph` URIs.
Large source and graph responses are capped at 500 records and provide a `next_cursor`. The shared
REST/MCP contract schema is available as `specimpact://contracts/v1` and `/api/contracts/v1`.

Source and Evidence Resources expose address and graph metadata only. Source body and Evidence
quotes are returned through approval-gated `prepare_*` or `open_evidence` tools.

The host can invoke these prompts:

- `/specimpact-onboard`
- `/specimpact-ingest`
- `/specimpact-change`
- `/specimpact-review`

## Locking And Jobs

Mutation execution holds `.specimpact/write.lock` across the operation. Durable history is stored
in `.specimpact/jobs.jsonl`. On first use, an existing `.specimpact/gui/jobs.jsonl` is copied into
the canonical ledger; the legacy file remains available as a v1.2 compatibility mirror.

MCP Tasks are not used as the durable baseline. The stable Job tools work across hosts and process
restarts. MCP SDK Tasks were removed from the core specification and are currently a deprecated
extension, so SpecImpact will add an adapter only if a host advertises a stable future extension.

## Approval Grant

External host transmission uses a metadata-only `TransmissionPreview`. A grant is bound to the
project, purpose, and source hash; it expires after ten minutes and can be consumed once. The token
is returned once and only its hash is persisted. `approved=true` is not an MCP authorization
contract.

The preview and grant ledgers do not store source bodies, prompt bodies, response bodies, or API
keys. The host workflow is detailed in [Host LLM Flow](host_llm.md).
