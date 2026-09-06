# Kernel phase 2: comparison, verification and coverage

- Implementation: deterministic bounded kernel; separate change-operation results, scoped
  identity, character/byte compatibility, conditional and contradictory claims, capacity versus
  input-limit rules, independent evidence strength, multiple paths and partial-result metadata.
- Files: semantic kernel, retrieval/atom attribution, relation normalization, ChangeAtom parser,
  adversarial tests, README, phase status and this review.
- Tests: focused kernel/Dirty Excel/Fintan retrieval: 34 passed; full suite pending.
- Lint: full ruff required before phase 3.
- Limitations: only direct confirmed property relations support typed conclusions; unverified
  transformations remain investigation candidates. Source-only matches are coverage gaps with
  Evidence IDs. These authored fixtures are not an independent enterprise holdout.
- Manual verification: `python -m pytest -q`; `python -m ruff check .`.
- README updated with kernel behavior.
- Scope: no persistence or transport integration yet.
- Future-phase leakage: no SQLite, future CLI or source connectors.

Full validation: 275 passed / 1 skipped (32.40s); ruff All checks passed. Removed business-specific injected aliases; fixed generic Japanese target parsing after the GUI regression exposed the dependency.
