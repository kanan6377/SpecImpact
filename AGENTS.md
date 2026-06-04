# AGENTS.md

## Project

SpecImpact is an evidence-first CLI tool for software design change impact analysis.

It ingests design documents and change requests, builds a lightweight local knowledge graph, and generates evidence-backed review reports.

## Core principles

1. Evidence-first, not confidence-first.
2. Review-assist, not auto-decision.
3. Local-first, not cloud-first.
4. Inspectable, not black-box.
5. Alias-aware, not naive semantic search.

## Non-goals

- Do not auto-edit design documents.
- Do not claim final impact decisions.
- Do not output uncalibrated confidence scores.
- Do not require Neo4j for default usage.
- Do not require external LLM calls for tests.
- Do not implement Web UI before v1.0.
- Do not implement Excel/PDF/docx in alpha-1.
- Do not implement future-phase code early.

## Phase-gated development

Proceed strictly phase by phase.

For each phase:
- Implement only that phase's scope.
- Do not create future-phase commands, modules, or placeholder files.
- Run pytest.
- Run ruff check.
- Update README and relevant docs.
- Write docs/reviews/<phase>.md.
- Update docs/phase_status.md.
- Continue only if the current phase passes tests and lint.

## Testing rules

- Unit tests must not call external LLM providers.
- Use FakeLLMClient in tests.
- Every model must have serialization/deserialization tests.
- Every CLI command must have at least one smoke test.
- Reports must have golden file tests where practical.
- pytest must pass before claiming completion.
- ruff check must pass before claiming completion.

## Review rules

Every phase must include:

- implementation summary
- changed files summary
- test results
- lint results
- known limitations
- manual verification commands
- README update
- scope check
- future-phase leakage check

## Output rules

Impact results must include:

- artifact_id
- display_name
- artifact_type
- review_priority
- evidence_strength
- match_type
- relation_distance
- rule_assessment
- relation_statuses
- reason
- relation_paths
- evidence_ids
- needs_review

Do not output confidence.

If an internal score is introduced later, document that it is not a probability.

## Privacy rules

- Do not send document chunks to an external provider without explicit configuration.
- If an external LLM is used, show a confirmation prompt.
- Do not log full document bodies by default.
- Unit tests must never require external API keys.
