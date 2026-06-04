# Phase Status

## v0.1.0-alpha-1

Status: complete

Scope:
- Markdown/txt ingest
- manual aliases.yml
- local JSONL store
- relation/evidence model
- analyze
- markdown/json report
- why
- credit_card_enrollment sample

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] docs/reviews/v0.1.0-alpha-1.md written
- [x] Manual commands verified
- [x] No future-phase files created

Notes: 5 tests passed. Manual demo generated 10 documents and 11 review candidates.

## v0.1.0-alpha-2

Status: complete

Scope:
- aliases suggest/list/approve/reject
- graph/evidence/artifact inspect
- income threshold and address required change cases

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] docs/reviews/v0.1.0-alpha-2.md written
- [x] Manual commands verified
- [x] No alpha-3 implementation files created

Notes: 8 tests passed. Manual runs generated 5 income and 6 address candidates.

## v0.1.0-alpha-3

Status: complete

Scope:
- trace.jsonl
- why-not
- status
- doctor --privacy
- eval metrics

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] docs/evaluation.md written
- [x] docs/privacy.md written
- [x] docs/reviews/v0.1.0-alpha-3.md written
- [x] Manual commands verified

Notes: 11 tests passed. Golden case recalls and evidence coverage are 1.0.

## v0.2.0

Status: complete

Scope:
- JSON schema stabilization
- relation status workflow
- alias edit UX
- evaluation dataset expansion

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] schema docs written
- [x] docs/reviews/v0.2.0.md written
- [x] Manual commands verified

Notes: 14 tests passed. Three-case dataset metrics are all 1.0.

## v0.3.0

Status: complete

Scope:
- OpenAPI YAML/JSON loader
- SQL DDL loader

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] docs/structured_loaders.md written
- [x] docs/reviews/v0.3.0.md written
- [x] Manual commands verified

Notes: 17 tests passed. Manual loader runs extracted 1 API and 2 tables.

## v0.4.0

Status: complete

Scope:
- CSV loader
- simple Excel loader

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] limitations documented
- [x] docs/reviews/v0.4.0.md written
- [x] Manual commands verified

Notes: 20 tests passed. Manual ingest extracted one CSV table and one Excel sheet.

## v0.5.0

Status: complete

Scope:
- optional Neo4j backend target
- Obsidian export
- review result import
- graph diff
- baseline comparison

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README updated
- [x] docs/integrations.md written
- [x] docs/reviews/v0.5.0.md written
- [x] Manual commands verified

Notes: 23 tests passed. Manual diff completed and backend was reset to local.

## v1.0.0

Status: blocked_publication_metadata

Scope:
- stable CLI/schema/local backend
- documented privacy and evaluation
- 3 sample projects
- 21 Golden/Evaluation/Holdout release cases with 20 distinct normalized oracle contents
- release validation

Completion checklist:
- [x] Implementation complete
- [x] pytest passes
- [x] ruff check passes
- [x] README Quickstart updated
- [x] Privacy and evaluation documented
- [x] 3 sample projects exist
- [x] 20-30 separated evaluation cases exist
- [x] Evaluation Must Review Recall >= 90%
- [x] No confidence field output
- [x] No external LLM calls in tests
- [x] docs/reviews/v1.0.0.md written
- [x] Manual release-check verified
- [x] External review remediation implemented
- [x] Convention-based generic parser verified
- [x] Quality release checks pass
- [ ] Replace placeholder repository URL
- [ ] Configure security contact

Notes: 66 tests pass. Quality release checks pass with 21 changes and 20 distinct normalized oracle
contents. Cross-type alias rejection, failed-ingest state preservation, schema mirror packaging,
source policy contact checks, exact privacy backend parsing, and CLI input errors are verified.
Publication remains blocked until repository URL and security contact placeholders are replaced.
