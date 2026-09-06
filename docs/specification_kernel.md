# Specification analysis kernel

The schema-v2 kernel models source assertions and individual change operations. Existing CLI,
MCP and Admin Console reports invoke it through `semantic/service.py`. The application version
remains 1.3.0 on this development branch; no release tag or registry package is published.

## Current supported contract

Labelled maximum-length constraints in Evidence text or simple tables can produce typed
assertions with explicit character/byte units. A change such as
`プロジェクト名の最大長を128文字から256文字へ変更` retains both values and units. Multiple
sentences/lines produce separate operations. Explicitly scoped entities disambiguate identical
names; existing unscoped graphs are not silently assigned invented scope.

Direct, confirmed, explicit property relations support bounded comparisons. API/input limits
must match the requested limit. Column/table capacity can exceed the requested maximum.
Unknown units, changed units, conditional text, conflicting source claims, conflicting change
operations, missing/stale evidence and unverified transformations remain unresolved.

The verifier checks persisted references, property binding and limited rules. It does not prove
that arbitrary source prose or LLM interpretations are correct. Review priority, evidence
strength and human decisions are independent. No confidence field is emitted.

Run the [end-to-end example](../examples/specification_kernel/README.md). Initially review the
unconfirmed relations; after explicit confirmation its expected results are API inconsistency,
sufficient column capacity and an unresolved byte interface. Sources are never edited.

## Inspection and migration

```powershell
specimpact analyze .\change.md --no-llm
specimpact analysis show
specimpact analysis replay
specimpact analysis export .\snapshot.json
specimpact analysis import .\snapshot.json
specimpact analysis decide <case-id> accepted --actor reviewer --reason "Read original"
```

The local `analysis.sqlite3` database owns normalized source snapshots, kernel results,
immutable report links and decision events. JSONL remains the ingestion intermediate used by
existing source viewers. Per-run `analysis.json` is a disposable projection. Export includes
Evidence quotes and is source material, not a metadata-only audit log. Import validates replay,
preserves old IDs and does not overwrite the local ingest graph. Keep an export and the original
workspace when moving between versions. Old analyses remain readable while replay across an
incompatible rule/extractor version fails explicitly.

Snapshots preserve normalized Evidence, not every original binary file. Dirty Excel originals
continue to use the existing source archive. Changed snapshots are recomputed; fine-grained
dependency invalidation and selective re-extraction are not implemented. Same input/schema/rules
produce the same content-addressed analysis identity. No network is needed for replay.

Each decision records an actor label, reason, case and analysis. The label is supplied by the
local user, not an authenticated enterprise identity. Existing GUI/CLI decisions are mirrored as
`local-user` events. A subsequent analysis preserves the human's prior status and exposes
`needs_revalidation` when its prerequisites differ; the old decision is not reused by the kernel.

## Host and compatibility surfaces

`prepare_impact_context` accepts `offset` and `limit` (1–100), returning total/next offset and
partial-page metadata. Candidate identity is `(artifact_id, atom_id)`. An omitted atom ID is
accepted only when that artifact has one prepared operation. Duplicate, cross-operation and
stale-snapshot submissions are rejected. Previously submitted pages are retained for the same
workspace fingerprint. Pending hypotheses are separate from submitted results and are recorded
in `host_submission_coverage.json` and the report API.

Typed cases are retained individually in `analysis show`; the v1 report groups by artifact and
uses the most urgent case for its summary. Candidates outside typed extraction keep the existing
review-assist behavior with an explicit unverified-comparison warning. They are not typed proofs.
MCP external source-content access still requires the existing preview and one-time approval.

## Evaluation and limitations

The new fixtures test identity, units, multiple operations/paths, unsupported text, stale and
missing evidence, contradictory claims, transactional rollback, replay integrity, independent
imports, CLI smoke, Host pagination/restart and transport consistency. The small Markdown example
has a golden outcome file and verifies that source bytes remain unchanged.

These are authored engineering regressions. Existing synthetic release cases and the selected
Fintan scenario are compatibility evidence. Independent enterprise holdout evaluation, realistic
large-corpus performance and human review-time savings have not been established. Current
extraction does not understand arbitrary Excel layouts, drawings, natural-language conditions,
numeric ranges, enums or unit conversions. Source-only matches appear as coverage gaps with
Evidence IDs. Coverage's denominator is the ingested inventory, not the entire real system.
