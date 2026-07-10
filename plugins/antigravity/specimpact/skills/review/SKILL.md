---
name: specimpact-review
description: Review SpecImpact proposals and persist explicit human impact decisions.
---

# Review

Load the Change Session and selected Impact. Use `open_evidence` only after elicitation or pass the
localhost one-time Grant token. Show the verifier reason and relation path before asking for a
decision.

Persist explicit choices with `set_impact_decision`, `resolve_alias`, or
`decide_graph_proposal`. Impact status may be `unreviewed`, `accepted`, `rejected`,
`needs_investigation`, `implemented`, `tested`, or `closed`. Render the Unified Review Artifact as
a projection; JSONL remains the source-of-truth.
