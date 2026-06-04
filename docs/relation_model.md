# Relation Model

Relations use stable `relation_id`, typed `source_id` and `target_id`, evidence references,
`extraction_method`, `polarity`, `status`, and `match_type`.

Status workflow: `unconfirmed` -> `confirmed` or `rejected`. Reviewers can revise status with
`specimpact relations set-status <relation-id> <status>`.

Rejected relations are excluded from impact candidates and recorded in trace output. Confirmed and
unconfirmed relations remain visible in impact `relation_statuses`.
