# Roadmap

## Delivered Foundation

- v1 local JSONL, stable CLI/report schema, Evidence-first release benchmark
- Dirty Excel normalization, Region detection, cell/range Evidence, original preservation
- LLM graph proposals, Alias review, Change Atoms, hybrid retrieval, Impact verifier
- Admin Console, source viewer, unified review, freshness, Jobs/Audit, Obsidian projection

## v1.3 Agent Host

- UI-independent Application Service shared by CLI, Web, and MCP
- typed stdio MCP Tools, Resources, Prompts, durable Jobs, idempotency, process locking
- Host LLM sampling and prepare/submit workflows with one-time privacy Grants
- Cursor Marketplace Plugin with Skills, Rules, Commands, Hook, and Canvas references
- Antigravity Plugin with Skills, Rules, Hook, Artifact templates, and installers
- host/CLI/provider/heuristic fallback order without weakening the Evidence verifier

## Next: Specification Evaluation

- Independently reviewed corpus split by system and workbook template
- Measure correction burden and review time against search and the legacy workflow
- Improve labelled extraction and selective re-analysis based on observed failure cases
- Expand typed rules beyond maximum length only after separate phase gates

The initial [specification kernel](specification_kernel.md) now provides versioned assertions,
bounded comparison, coverage, replay and snapshot-bound review. Full binary source archiving,
arbitrary conditions and transformations are still outside its current typed contract.

## Later: Enterprise Sources

- SharePoint and Microsoft Graph source connector with tenant policy controls
- OneDrive version metadata and remote source freshness
- optional M365 Copilot remote MCP deployment profile
- signed Plugin releases and automated Marketplace publishing

These connectors must preserve the same preview, Grant, redaction, workspace/tenant boundary, and
metadata-only audit contracts. They will not be mixed into the v1.3 local/synced-folder release.

## Later: Review Surfaces

- VS Code extension/custom viewer only if it adds evidence navigation unavailable through MCP
- NotebookLM Enterprise export/hand-off when a supported write-back contract exists
- optional MCP Apps review component after stable support across target hosts
- richer Office-compatible workbook rendering without automatic source editing

Host chat, Canvas, Artifact, Obsidian, and future views remain projections. JSONL Change Sessions,
Impact Decisions, Proposals, Aliases, relation status, and Evidence remain authoritative.
