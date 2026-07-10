# Changelog

## 1.3.0 - Agent Host

### Added

- UI-independent Application Service and shared Pydantic REST/MCP contracts.
- Workspace-scoped MCP stdio server with typed tools, resources, prompts, durable Jobs,
  idempotency, and process locking.
- Host LLM Dirty Excel, Change Atom, and Impact prepare/submit workflows with verifier enforcement.
- Ten-minute, one-time, project/purpose/source-bound Approval Grants and localhost fallback UI.
- Cursor Marketplace Plugin with Skills, Rules, Commands, Hook, and Canvas references.
- Antigravity Plugin with Skills, Rules, Hook, Artifact templates, and installers.
- Agent runtime doctor, privacy-safe source-change notifications, and GitHub CI.
- A six-workbook Dirty SIer benchmark and Agent Host E2E covering screen, validation, API, DB,
  external interface, boundary-test impacts, persisted decisions, and Obsidian projection.
- Header-signature-first Dirty Excel classification so embedded revision blocks do not mask DB or
  validation tables.

### Compatibility

- Existing CLI, FastAPI Admin Console, v1 report schema, local JSONL, Dirty Excel, providers,
  Obsidian export, evaluation, and release benchmark remain available.
- `.specimpact/gui/jobs.jsonl` is retained as a compatibility mirror; the canonical ledger is now
  `.specimpact/jobs.jsonl`.

### Security

- MCP source paths reject workspace escape and symlink escape.
- Source/Evidence MCP Resources are metadata-only; content is returned by approval-gated tools.
- Host audit stores hashes and IDs, never source, prompt, response, key, or token bodies.
