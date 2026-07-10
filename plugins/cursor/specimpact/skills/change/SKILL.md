---
name: specimpact-change
description: Convert a requested design change into evidence-bound Change Atoms and verified impact hypotheses. Use when a user asks what a change may affect.
---

# SpecImpact Change

## Workflow

1. Ask for a precise proposed change. Preserve target, property, before value, after value, and
   any stated constraints. Do not silently fill missing values from guesswork.
2. Call `prepare_change` with `sample_with_host=false`. If SpecImpact requests approval, show the
   metadata-only transmission preview and wait for explicit approval before using returned content.
3. Produce a schema-valid Change Atom proposal using only returned Evidence IDs. Submit it through
   `submit_change_atoms` with a unique idempotency key.
4. Read the resulting session with `get_change_session`. Call `prepare_impact_context` with
   `sample_with_host=false`, obtain approval when required, then submit a schema-valid impact
   hypothesis through `submit_impact_hypotheses` with another unique idempotency key.
5. Treat all host reasoning as a proposal. SpecImpact verification may lower the priority and
   evidence-free claims remain non-final. Never state that `must_review` is established solely by
   an agent recommendation.
6. Present the Impact Review projection. State that JSONL and the persisted report remain the
   authoritative record.

## Reference

Read the shared `skills/review/references/canvases/impact-review.md` template when presenting the
impact projection.
