# Kernel phase 4: shared analysis and transport integration

- Implementation: existing CLI, provider and Application/Console flows persist and project
  one kernel result. Typed cases retain separate operation IDs; v1 reports aggregate by artifact.
  Host prepare pages retain operation IDs and workspace fingerprints, validate candidate-specific
  Evidence and reject stale submissions; submitted pages survive restart. Untyped fallback
  candidates carry explicit warnings. Evidence strength is independent of LLM priority changes.
  Added analysis show/replay/export/import/decide commands and snapshot-bound decision history.
- Files: semantic service, CLI/core/report store, HostWorkflow/MCP, Application report projection,
  decision store, legacy verifier/hypothesis generation, alias schema, tests and documentation.
- Tests: focused integration/Host/Dirty Excel: 31 passed. Full suite pending.
- Lint: ruff passes before full validation.
- Limitations: compatibility reports group artifacts; inspect typed cases for operation detail.
  Unsupported properties preserve legacy review assistance. Conditional/transform semantics
  remain unresolved. Console uses existing report reasons/warnings and API projection, with no
  new frontend screens. Review status is preserved when prerequisites change; a separate
  `needs_revalidation` flag indicates that the old decision does not cover the new snapshot.
- Manual: `python -m pytest -q`; `python -m ruff check .`; `specimpact analysis show`;
  `specimpact analysis replay` after a normal analysis.
- README and CLI updated; existing output fields and external approval boundaries preserved.
- Scope: common kernel integration and review provenance. Alias confidence labels removed in
  favor of unresolved questions; old stored labels are ignored during deserialization.
- Future-phase leakage: no new source connectors, source auto-edits or unrelated UI work.

Full validation: 288 passed / 1 skipped (52.84s); ruff All checks passed. Host pending hypotheses are reported separately, and assertion-specific verification prevents an unrelated confirmed path from validating a property.
