# Kernel phase 1: typed specification model

- Implementation: strict length values, version-bound anchors, scoped mentions/identities,
  labelled text/table assertions, independent change operations and explicit units.
- Files: `semantic/models.py`, `semantic/extraction.py`, package exports, existing Entity and
  ChangeAtom models/parser, `tests/test_semantic_models.py`, README and phase status.
- Tests: focused model and parser tests: 21 passed. Full suite pending below.
- Lint: focused ruff passes. Full ruff required before phase 2.
- Limitations: label-based extraction only; unlabelled numeric cells remain unresolved;
  legacy source hashes identify the ingested representation, not a new verified raw blob.
- Manual verification: `python -m pytest -q`; `python -m ruff check .`.
- README updated with available typed model behavior.
- Scope: semantic representation and deterministic extraction, preserving existing output schema.
- Future-phase leakage: no analysis rules, SQLite repository, new CLI or transport code.

Full validation: 260 passed / 1 skipped (35.18s); ruff All checks passed.
