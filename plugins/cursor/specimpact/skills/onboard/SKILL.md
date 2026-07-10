---
name: specimpact-onboard
description: Initialize a SpecImpact workspace and build an evidence graph from local design sources. Use for first-time setup, workspace onboarding, or design-document ingestion.
---

# SpecImpact Onboard

## Preconditions

- The `specimpact` executable must already be installed with MCP support.
- The current Cursor workspace is the project passed to the MCP server.
- Do not add, vendor, or modify the SpecImpact Python package from this plugin.

## Workflow

1. Read the `specimpact://projects/<project_id>` resource or invoke the `specimpact-onboard` MCP
   prompt. If onboarding is required, ask the user before running `specimpact init` in the
   workspace.
2. Ask the user to select the local source directory and its source mode when not clear. Use
   `ingest_sources` with an idempotency key and one of `markdown`, `dirty-excel`, `excel`, `csv`,
   `openapi`, or `ddl`.
3. Poll `get_job` until the durable ingestion job reaches a terminal state. Do not infer success
   from a queued job.
4. For Dirty Excel, obtain local region metadata, call `prepare_graph_context` with
   `sample_with_host=false`, and require the transmission preview approval before working with
   returned content. Submit a schema-valid extraction through `submit_graph_extraction` with a
   new idempotency key.
5. Keep graph extractions and aliases pending until a human uses the associated review action.
   Do not claim that an alias, relation, or graph proposal is accepted before it is persisted.
6. Use the Evidence Graph projection below for a compact handoff. It is a markdown view of local
   JSONL, not a writable Canvas or source of truth.

## Local Samples

- Markdown design documents: `examples/credit_card_enrollment/docs/`
- Dirty Excel design documents: `examples/dirty_sier_excel/docs/`
- The matching change requests and aliases are kept beside each sample under `changes/` and
  `aliases.yml`.

## Reference

Read the shared `skills/review/references/canvases/evidence-graph.md` template when presenting the
graph projection.
