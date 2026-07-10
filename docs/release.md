# v1.2 Release Validation

The release manifest contains 21 change cases and 20 distinct normalized oracle contents separated
into Golden, Evaluation, and Holdout categories. Holdout includes the separate Payment Processing
sample domain.
Run:

```powershell
specimpact release-check ./examples/evaluation/release_cases.yml
```

The command checks the 20-30 case range, unique changes, normalized oracle content hashes, category
presence, Evaluation Must Review Recall >= 90%, visible precision >= 70%, evidence coverage,
report size, candidate expansion ratio, configured repository metadata, matching security contact,
and absence of `confidence` and legacy `llm_judgement` fields.

The release gate validates review-candidate recall, not final impact correctness. Publish release
wheels only after `release-check`, `pytest -q`, `ruff check .`, and
`python -m compileall -q specimpact` pass from a clean environment.

The v1.2 GUI release also requires `npm run check`, `npm run build`, localhost browser verification,
keyboard access to review and graph selection, no horizontal page overflow at 390 px, no current
console errors, and confirmation that the Cytoscape chunk is loaded only on the Graph view.
