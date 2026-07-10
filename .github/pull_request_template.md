## Summary

## Evidence / Review Behavior

## Compatibility

- [ ] Existing CLI, report schema, JSONL, and Admin Console behavior is preserved or documented.
- [ ] LLM output remains a proposal/hypothesis and cannot bypass the verifier.
- [ ] External content requires preview and approval.
- [ ] Tests use Fake Host/FakeLLM and no external API key.

## Verification

- [ ] `pytest -q`
- [ ] `ruff check .`
- [ ] `python -m compileall -q specimpact`
- [ ] `specimpact release-check ./examples/evaluation/release_cases.yml`
