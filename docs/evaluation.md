# Evaluation

`specimpact eval --expected <file>` compares the latest local report with an expected result.
Alpha-3 metrics are Must Review Recall, Should Review Recall, Evidence Coverage, and Report Size.
These are review-assist quality indicators, not probabilities and not final impact decisions.

v1.0 separates Golden, Evaluation, and unknown-domain Holdout cases in
`examples/evaluation/release_cases.yml`. Use `specimpact release-check` for release validation.
The release gate checks recall, precision, evidence coverage, report size, candidate expansion,
unique changes, and normalized oracle content hashes. Case IDs and array ordering cannot make
duplicated expected results appear independent.
