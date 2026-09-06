# Kernel phase 5: engineering delivery

- Implementation summary: published a real Markdown ingestion walkthrough with three different
  constraint outcomes; synchronized user, architecture, roadmap, Evidence, privacy and migration
  documentation. Moved shared process locking out of Application to fix a standalone-import
  cycle found by the independent walkthrough test.
- Changed files: fixture documents/aliases/expected JSON/README; walkthrough test; shared locking
  module and compatibility import; public documentation, changelog and phase status.
- Test results: 292 passed / 1 skipped (52.19s). Existing release-check: all 21 cases pass.
- Lint results: ruff All checks passed; compileall and git diff --check passed.
- Known limitations: maximum length is the only typed rule family; normalized-source snapshots,
  full recomputation on changed inputs, legacy JSONL ingestion, current-source binary viewer,
  authored regressions rather than independent enterprise evaluation. Human review-time savings
  are unmeasured. No package registry publication or release tag is included.
- Manual verification: `python -m pytest -q`; `python -m ruff check .`;
  `python -m specimpact release-check examples/evaluation/release_cases.yml`;
  `python -m compileall -q specimpact`; `npm run check` and `npm run build` in frontend;
  `python -m build --wheel`; installed-wheel CLI/MCP import and walkthrough smoke.
- README update: current behavior, walkthrough and explicit limits linked.
- Scope check: engineering implementation and branch push; user research remains a follow-up,
  not a completed or claimed performance result.
- Future-phase leakage check: no cloud connectors, PDF/docx/image interpretation, source editing,
  new frontend screens, arbitrary business-rule execution or external LLM tests.

## Final validation, 2026-09-06

- TypeScript check and Vite production build: passed; no frontend source change required.
- Wheel build: `specimpact-1.3.0-py3-none-any.whl` built successfully. Existing setuptools
  license-metadata deprecation warnings remain; they do not fail this build.
- Installed wheel in a separate temporary package directory: isolated Python imported the
  installed package, repository and MCP factory; CLI version/init/ingest/analyze/show/replay passed.
- Standalone repository/CLI subprocess import is now a regression test, preventing full-suite
  import ordering from hiding the former cycle.
- Host request-file mutation is rejected before advice is stored; report Evidence comes from
  the saved snapshot after re-ingestion. Both have regression tests.
- Existing release dataset reports recall/visible precision/Evidence coverage 1.0 for its fixed
  cases. This is compatibility evidence only, not a measurement of enterprise generalization.
- Full current-corpus Fintan fetch/Host LLM experiment was not rerun; focused existing regressions
  are part of pytest. No external LLM provider or API key was required.
- Git delivery target: `origin/codex/specification-kernel`. No force push, main merge, release tag
  or package-registry publication is included.
