# Evaluation

`specimpact eval --expected <file>` compares the latest local report with an expected result.
Alpha-3 metrics are Must Review Recall, Should Review Recall, Evidence Coverage, and Report Size.
These are review-assist quality indicators, not probabilities and not final impact decisions.

v1.0 separates Golden, Evaluation, and unknown-domain Holdout cases in
`examples/evaluation/release_cases.yml`. Use `specimpact release-check` for release validation.
The release gate checks recall, precision, evidence coverage, report size, candidate expansion,
unique changes, and normalized oracle content hashes. Case IDs and array ordering cannot make
duplicated expected results appear independent.

## Known Evaluation Limits

- The bundled dataset is synthetic-sample heavy.
- There is no large legacy Excel corpus yet.
- There is no real enterprise design document benchmark yet.
- Metrics are for review-candidate recall and visible precision, not final impact correctness.
- Dirty input, alias collisions, false positives, and important candidates hidden by ranking should
  be reviewed separately during adoption.

The later [Fintan experiment](reviews/fintan-compatibility-benchmark.md) covers selected public
design workbooks for one maximum-length change. It does not establish general enterprise accuracy.
The [kernel walkthrough](../examples/specification_kernel/README.md) and semantic tests add
authored adversarial and transactional regressions; they are not independent holdout evidence.
