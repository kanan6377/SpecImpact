---
name: specimpact-ingest
description: Ingest selected local design sources into SpecImpact with durable job tracking and evidence-safe host handling. Use for Markdown, Excel, CSV, OpenAPI, or DDL sources.
---

# SpecImpact Ingest

## Workflow

1. Confirm the requested path resolves inside the current workspace. Do not ingest a path outside
   the project boundary.
2. Call `ingest_sources` with the correct mode and a unique idempotency key. This is a local
   operation; it does not authorize external document transmission.
3. Poll `get_job` or inspect `list_jobs` until the job succeeds, fails, or is cancelled. Report
   the job ID and final status without printing source bodies.
4. For a Dirty Excel result, continue through `prepare_graph_context` and
   `submit_graph_extraction` as an evidence-bound proposal workflow. Request
   `sample_with_host=false`; Cursor is not declared as an MCP sampling host by this plugin.
5. When source or evidence content is withheld, present the transmission preview metadata and
   wait for explicit user approval. A declined or unavailable approval ends that content path.
6. Do not auto-accept graph proposals or alias candidates.

## Output

Report the source path, mode, job ID, terminal status, returned IDs, and next human review step.
Do not add confidence values or quote full documents.
