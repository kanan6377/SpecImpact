---
name: specimpact-onboard
description: Initialize a SpecImpact workspace and build an evidence-backed design graph.
---

# Onboard

Read the project MCP Resource. If initialization is required, ask the user to run
`specimpact init` in this workspace. Ingest selected sources with `ingest_sources` and poll the
durable Job.

For Dirty Excel, use returned Region IDs with `prepare_graph_context`. If content is withheld and
the host cannot elicit, open `approval_url`, ask the user to approve, and pass the displayed token
once to `authorize_prepared_context`. Submit the schema-valid result with
`submit_graph_extraction`. Never auto-accept the Graph Proposal.

Use `examples/dirty_sier_excel` for the first guided run. Present the Evidence Graph Artifact after
ingestion and keep JSONL authoritative.
