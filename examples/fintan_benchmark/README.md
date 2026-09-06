# Fintan benchmark corpus

This manifest defines the supervisor-baseline 21-workbook subset for the `project-name 128→256` scenario:

- domain definition and A1 table definition
- screen function specifications WA10201, WA10202, WA10203, and WA10206
- batch function specifications BA10601, BA10602, and BA10603
- external interface specifications N21AA001, N21AA002, and N21AA003
- screen and batch message specifications
- screen unit-test specifications WA10201, WA10202, WA10203, and WA10206
- batch unit-test specifications BA10601, BA10602, and BA10603

It pins the source repository and commit and assigns stable local filenames that preserve each workbook's type and code. The fetcher extracts only those blobs with git plumbing commands; it does not check out the repository. The output directory contains the 21 `.xlsx` files and `provenance.json`, including source paths, local names, and SHA-256 hashes.

The documents are provided under the [Fintan contents terms](https://fintan.jp/page/295/#Fintan%E3%82%B3%E3%83%B3%E3%83%86%E3%83%B3%E3%83%84%E4%BD%BF%E7%94%A8%E8%A8%B1%E8%AB%BE%E6%9D%A1%E9%A0%85); source code in the upstream repository is Apache License 2.0.

## Reproduce

Run from the repository root:

```powershell
specimpact benchmark fetch-fintan .\temp\fintan-corpus
specimpact benchmark run-fintan .\temp\fintan-corpus `
  --workspace .\temp\fintan-workspace `
  --aliases .\examples\fintan_benchmark\aliases.yml `
  --change .\examples\fintan_benchmark\change_project_name_length.md `
  --expected .\examples\fintan_benchmark\expected_project_name_length.json
```

The deterministic run reports expected-workbook recall, negative-control precision, Evidence and cell-address coverage, unknown-sheet rate, and visible candidate count. The measured baseline found 19/19 expected workbooks, zero false positives, 20/20 Evidence anchors, 100% Evidence/cell coverage, 0% unknown sheets, and 40 visible candidates.

The source workbooks are not vendored in this repository. The fetcher records the pinned commit, source paths, local names, and SHA-256 in `provenance.json`; use of the documents remains subject to the Fintan contents terms and attribution requirements.

See the [compatibility benchmark report](../../docs/reviews/fintan-compatibility-benchmark.md) for the Host LLM experiment, limitations, and acceptance gates.
