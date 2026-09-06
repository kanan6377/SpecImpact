# Kernel phase 3: transactional analysis repository

- Implementation: SQLite owns immutable normalized-source snapshots, results and decision events.
  Atomic snapshot/run insertion, immutable report links, content integrity verification,
  deterministic replay and validated JSON export/import. Changes produce separate versions;
  unchanged analysis inputs reuse the same content-addressed result. Old decisions stay bound
  to their original analysis and are never automatically applied to new inputs.
- Files: semantic repository, process lock reentrancy, legacy graph merge lock/health marker,
  repository tests, README, phase status and this review.
- Tests: focused storage/process-lock suite: 10 passed / 1 skipped; full suite pending.
- Lint: full ruff required before phase 4.
- Limitations: snapshots preserve normalized evidence, not a full binary copy of every source.
  Existing Dirty Excel originals remain in the legacy source archive. Legacy JSONL ingestion is
  not a multi-file SQLite transaction; interrupted merges are surfaced as coverage gaps. An
  import preserves source references and does not grant access to original external paths.
- Manual verification: `python -m pytest -q`; `python -m ruff check .`.
- README updated to distinguish legacy ingest data from authoritative new analysis history.
- Scope check: local snapshot storage, recovery, replay and decision provenance only.
- Future-phase leakage: no new CLI, MCP changes, frontend changes or cloud connectors.

Full validation: 280 passed / 1 skipped (45.46s); ruff All checks passed. Preflight validation runs before marking a graph merge as writing, preserving failed-ingest state.
