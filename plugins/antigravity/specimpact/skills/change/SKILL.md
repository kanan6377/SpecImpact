---
name: specimpact-change
description: Convert a natural-language design change into verified Change Atoms and impacts.
---

# Change

Ask for target, property, before value, and after value. Call `prepare_change`, complete the
approval flow, and return a schema-valid submission through `submit_change_atoms`.

Next call `prepare_impact_context`. Investigative subagents may inspect screen, API, DB, external
IF, validation, and tests in parallel, but all results must return through one
`submit_impact_hypotheses` call and the single SpecImpact verifier. Include concrete required
actions, warnings, uncertainty, graph paths, and Evidence IDs. Never decide human status.
