# Specification kernel implementation contract

Approved direction: `../redesign_direction_ja.md`. Engineering delivery retains existing CLI,
MCP and review surfaces, replacing their shared semantic analysis in sequential phases.
No automatic source editing, external test providers, or future source connectors are included.

## Acceptance gates fixed before implementation

0. Preserve the existing 249-test baseline and release dataset; document architecture and gates.
1. Strict, serializable source anchors, mentions, assertions and typed change operations;
   multiple operations retain identity; deterministic extraction never interprets an arbitrary
   number as a length constraint. Existing v1 contracts remain readable.
2. One bounded analysis kernel: operation-scoped identity, typed length comparison, unit and
   condition checks, supported dependency paths, contradictions, rejected/stale evidence,
   disconnected source mentions and explicit coverage/truncation. Test adversarial examples
   including capacity already sufficient, bytes versus characters, same-name different scope,
   multiple operations, irrelevant old values, and missing sources. No confidence output.
3. Immutable analysis snapshots and replay in a transactional local SQLite analysis repository;
   legacy JSONL graph import is explicit and non-destructive. JSONL remains the legacy ingest
   workspace and compatibility projection, not a second authority for persisted kernel runs.
   Verify rollback, content-addressed snapshots, replay integrity, and decision provenance.
4. Integrate the kernel into existing report persistence and CLI/MCP/Host/Console projections;
   share verification and preserve legacy candidates for unsupported properties as unverified
   review assistance. Bind Host candidates to operation IDs and snapshot hashes; reject stale
   submissions and cross-operation evidence. Provide CLI inspection and replay smoke tests.
5. Publish documentation, fixtures and measured engineering evaluation; validate pytest, ruff,
   release-check, frontend and distribution. Push the tested branch.

## Deliberate boundaries

The first typed constraint is maximum length. Arbitrary natural-language conditions, numeric
ranges, enum, image semantics and transformations are recorded as unresolved, not implemented
prematurely. The legacy graph remains an ingestion intermediate; the immutable analysis store
owns new snapshots, runs and decision events. Full replacement of all legacy workspace JSONL
is not necessary to make analysis transactional and would unnecessarily couple migration to
existing GUI source viewers. A monolithic relational database and network deployment are out
of scope. Legacy reports remain available; new semantic details are versioned and additive.

Source claims are not system truth. Strong structural grounding is independent of priority.
No detected inconsistency applies only to the checked property, unit, scope and conditions.
Stored extraction and rule versions support deterministic replay; LLM regeneration does not.

The new adversarial fixtures are engineering regression cases authored during implementation,
not an independently reviewed enterprise holdout. Human review-time savings and enterprise
generalization require external participants/data and must not be claimed from these tests.

## Phase 0 baseline

Current baseline: commit d92c42d, 249 passed / 1 skipped, ruff passes (2026-09-06).
Fintan's reported 19/19 workbooks is one selected change scenario, not general impact accuracy.
Known reproducible code-level defects: first-atom attribution, priority-derived evidence
strength, unscoped prior decisions and substring matching of before values. Their replacement
is tested against semantic expectations, not by preserving incorrect outputs.
