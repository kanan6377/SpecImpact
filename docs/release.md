# v1.0 Release Validation

The release manifest contains 21 change cases and 20 distinct normalized oracle contents separated
into Golden, Evaluation, and Holdout categories. Holdout includes the separate Payment Processing
sample domain.
Run:

```powershell
specimpact release-check ./examples/evaluation/release_cases.yml
```

The command checks the 20-30 case range, unique changes, normalized oracle content hashes, category
presence, Evaluation Must Review Recall >= 90%, visible precision >= 70%, evidence coverage,
report size, candidate expansion ratio, and absence of `confidence` and legacy `llm_judgement`
fields.

Publication also requires replacing the placeholder repository URL in `pyproject.toml` and the
`SECURITY-CONTACT-TODO` marker in `SECURITY.md` and `specimpact/resources/publication.json`.
Generate release wheels only after those values are configured and `release-check` passes.
Source-tree validation requires the contact in `SECURITY.md` to match the packaged publication
metadata.
