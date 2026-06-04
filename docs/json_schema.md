# JSON Schema Contract

The v1.0 JSON contract has one source of truth under `schemas/v1/`. Development runs validate
against that directory. Wheel builds copy the same files into package data, and installed wheels
validate generated reports, relations, and evidence records against the packaged copy.

Schema identifiers use stable `urn:specimpact:schema:v1:*` values. They do not depend on a
placeholder repository URL.

Required impact fields are `artifact_id`, `display_name`, `artifact_type`, `review_priority`,
`evidence_strength`, `match_type`, `relation_distance`, `rule_assessment`, `reason`,
`relation_paths`, `evidence_ids`, `relation_statuses`, and `needs_review`.

`evidence_strength` is an explainable classification derived from evidence and relation type. It
is not a probability. SpecImpact does not emit a `confidence` field.

## v1.1 Optional Fields

When optional LLM reranking is enabled, impacts may also contain `llm_judgement`, `llm_reason`,
and `selected_evidence_ids`. They are advisory fields. Guardrails prevent them from downgrading
rule-based direct or explicit `must_review` candidates or independently promoting a candidate to
`must_review`.
