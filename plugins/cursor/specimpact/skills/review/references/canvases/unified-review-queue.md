# Unified Review Queue Canvas

> Projection only. This template combines reviewable records for scanning; it does not persist
> decisions. Use the corresponding SpecImpact review tool with an explicit human decision.

## Queue

| Kind | ID | Subject | Evidence | Status | Next human action |
| --- | --- | --- | --- | --- | --- |
| Impact | `<impact_id>` | `<artifact_id>` | `<evidence_ids>` | `<review status>` | `<decision or investigation>` |
| Graph proposal | `<proposal_id>` | `<relation or node>` | `<evidence_ids>` | `<pending|accepted|rejected>` | `<accept or reject>` |
| Alias candidate | `<candidate_id>` | `<alias pair>` | `<evidence_ids>` | `<pending|confirmed|rejected>` | `<confirm or reject>` |

## Review Guardrails

- A recommendation is not a decision.
- Evidence bodies require the SpecImpact approval flow.
- Use one unique idempotency key per persisted mutation.
- Do not add a confidence score.
