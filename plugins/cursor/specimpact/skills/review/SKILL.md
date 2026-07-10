---
name: specimpact-review
description: Review SpecImpact impact candidates with evidence, relation paths, and explicit human decision states. Use for impact triage, alias review, graph proposal review, or report handoff.
---

# SpecImpact Review

## Workflow

1. Read the latest impact session, impact resource, and metadata. For a specific claim, call
   `open_evidence` and wait for its explicit approval flow before viewing evidence content.
2. For every candidate, retain all required output fields: `artifact_id`, `display_name`,
   `artifact_type`, `review_priority`, `evidence_strength`, `match_type`, `relation_distance`,
   `rule_assessment`, `relation_statuses`, `reason`, `relation_paths`, `evidence_ids`, and
   `needs_review`.
3. Explain the evidence and relation path, then ask for a human decision. Use
   `set_impact_decision` only for an explicit human state change and attach a concise reason.
4. Use `resolve_alias` and `decide_graph_proposal` only after the user chooses the confirmation or
   rejection. Every mutation needs a unique idempotency key.
5. Do not convert a review priority into a final delivery decision. Do not output confidence.
6. Render the Unified Review Queue projection for handoff. It is a read-only markdown template;
   `.specimpact/*.jsonl` and the persisted report are authoritative.

## Reference

Read [Unified Review Queue Canvas](references/canvases/unified-review-queue.md) when presenting
the review projection.
