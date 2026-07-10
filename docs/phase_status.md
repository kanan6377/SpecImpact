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

Status: complete

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
- [x] Configure repository URL
- [x] Configure security contact

Notes: 118 tests pass. Quality release checks pass with 21 changes and 20 distinct normalized oracle
contents. Cross-type alias rejection, failed-ingest state preservation, schema mirror packaging,
source policy contact checks, exact privacy backend parsing, and CLI input errors are verified.
The release metrics validate review-candidate recall and evidence coverage for the bundled
Golden/Evaluation/Holdout cases. They do not claim final impact correctness on arbitrary enterprise
documents.

## v1.2.0 UX Phase 0

Status: complete

Scope:
- current production GUI audit
- evidence review workspace information architecture
- design-system and accessibility requirements
- measurable UX completion criteria
- frontend architecture decision
- public/private IP development boundary

Completion checklist:
- [x] UX audit written
- [x] Target information architecture written
- [x] Design and accessibility requirements written
- [x] Completion metrics written
- [x] README updated
- [x] `docs/reviews/v1.2.0-ux-phase-0.md` written
- [x] pytest passes (137 tests)
- [x] ruff check passes
- [x] compileall passes
- [x] Manual documentation verification complete
- [x] No future-phase implementation files created

Notes: This phase intentionally contains documentation and architecture decisions only. Production
frontend migration begins after this phase passes all gates. `pytest -q` completed with 137 passing
tests; ruff and compileall also passed.

## v1.2.0 UX Phase 1

Status: complete

Scope:
- production mock-data removal
- React/TypeScript/Vite build foundation
- six URL-addressable workspace views
- legacy route compatibility
- packaged local static assets
- desktop and narrow-width accessibility baseline

Completion checklist:
- [x] Production GUI uses typed project APIs without `SI_DATA`
- [x] Runtime CDN and remote font dependencies removed
- [x] Legacy routes redirect with `project_id` preserved
- [x] Frontend TypeScript check and production build pass
- [x] Real-project browser verification complete
- [x] 390 px responsive verification complete
- [x] README and GUI manual updated
- [x] `docs/reviews/v1.2.0-ux-phase-1.md` written
- [x] Full pytest passes (137 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: Phase 1 establishes the production frontend and application shell. Onboarding, Source Library,
expanded review decisions, source freshness, and patent-sensitive private validation remain in their
assigned later phases.

## v1.2.0 UX Phase 2

Status: complete

Scope:
- GUI-native project onboarding
- guided sample creation
- managed design-source upload
- Source Library summary API and responsive view
- existing queue/privacy/consent integration

Completion checklist:
- [x] Project creation initializes a local SpecImpact store
- [x] Guided sample runs from the onboarding screen
- [x] Documents, Dirty Excel, OpenAPI, DDL, and CSV are supported
- [x] Source Library uses persisted project data
- [x] External preview and project queue remain authoritative
- [x] Source API and managed-ingest tests pass
- [x] Desktop and 390 px browser verification complete
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-2.md` written
- [x] Full pytest passes (138 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: Source Library deliberately reports current ingestion state only. Version history, graph diff,
and stale propagation remain Phase 5 work.

## v1.2.0 UX Phase 3

Status: complete

Scope:
- selected design-document Graph Context
- candidate/source/evidence deep links
- evidence-to-source focus navigation
- verifier detail presentation
- change-review reload restoration

Completion checklist:
- [x] Selected source contributes document and graph context
- [x] Candidate, source, and evidence selections are URL-addressable
- [x] Evidence opens its exact highlighted source location
- [x] Reload restores the same review position
- [x] Verifier fields are visible in the Inspector
- [x] Selected-source context regression test passes
- [x] Real-project browser verification complete
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-3.md` written
- [x] Full pytest passes (139 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: Decision mutations remain assigned to Phase 4. This phase improves analysis context and
navigation without changing priority semantics or finalizing impacts automatically.

## v1.2.0 UX Phase 4

Status: complete

Scope:
- unified graph/alias/relation/impact review queue
- unresolved mention visibility
- graph proposal diff preview
- evidence-backed decision controls
- project-queue persisted mutations

Completion checklist:
- [x] All review families share one API and view
- [x] Graph proposals show node/edge diff before decision
- [x] Alias candidates show comparison context
- [x] Relation and Impact status controls are functional
- [x] Evidence quotes are visible in the decision context
- [x] Mutations run through project jobs and core services
- [x] Aggregation and persistence regression test passes
- [x] Desktop and 390 px browser verification complete
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-4.md` written
- [x] Full pytest passes (140 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: Unresolved mentions remain investigation items. Source freshness and stale-decision handling
are assigned to Phase 5.

## v1.2.0 UX Phase 5

Status: complete

Scope:
- additive source-version history
- transaction-linked relation graph diff
- evidence/node/relation/impact stale propagation
- stale resolution on human re-review
- Source Library, Graph, and Review Queue freshness presentation

Completion checklist:
- [x] Initial and modified source versions are recorded
- [x] Relation additions, removals, and changes share a merge transaction ID
- [x] Changed source dependencies become stale
- [x] Confirmed affected relations return to unconfirmed
- [x] Relation/Impact re-review resolves matching stale records
- [x] Source Library and Graph expose freshness state
- [x] Graph diffs are reviewable from the unified queue
- [x] New models have serialization tests
- [x] Browser compatibility verification complete
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-5.md` written
- [x] Full pytest passes (142 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: v1 collections and report schemas remain unchanged. The freshness collections are local
JSONL audit records.

## v1.2.0 UX Phase 6

Status: complete

Scope:
- confidential invention record outside Git
- primary-source prior-art orientation
- measurable technical-effect experiment protocol
- filing and public-disclosure gate
- public/private implementation boundary audit

Completion checklist:
- [x] Confidential workspace exists outside the repository
- [x] Disclosure draft and contributor/inventorship placeholders exist
- [x] Initial prior-art matrix uses primary patent publications
- [x] Experiment metrics, thresholds, controls, and stop conditions are defined
- [x] Filing decision is explicitly HOLD
- [x] No confidential implementation or placeholder entered public source
- [x] `docs/reviews/v1.2.0-ux-phase-6.md` written
- [x] Full pytest passes (142 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: No patentability conclusion is claimed. Professional patent advice and measured technical
effect are required before the gate can change.

## v1.2.0 UX Phase 7

Status: complete

Scope:
- GUI-native Obsidian knowledge-graph export
- allowlisted LLM transmission audit and review replay
- expanded external payload redaction
- failed-job recovery guidance

Completion checklist:
- [x] Obsidian export preview and project job are available in the GUI
- [x] Artifact, Evidence, Change, Impact, Dashboard, and Canvas output remains supported
- [x] Audit API excludes prompt/source/response bodies
- [x] Review replay exposes bounded reconstruction metadata
- [x] Common labeled identifiers and sensitive keys are redacted
- [x] Failed jobs show action-specific recovery guidance
- [x] Service, API, export, and redaction tests added
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-7.md` written
- [x] Full pytest passes (144 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: Obsidian is a review projection. Local JSONL remains the system of record, and external
transmission still requires explicit approval.

## v1.2.0 UX Phase 8

Status: complete

Scope:
- keyboard and focus accessibility
- responsive review behavior
- graph keyboard alternative and lazy loading
- localhost metadata and final release documentation

Completion checklist:
- [x] External transmission uses a native dialog instead of `window.confirm`
- [x] Skip link and visible focus are available
- [x] Graph elements are selectable without pointer input
- [x] Mobile review starts with candidates and opens Inspector on selection
- [x] Cytoscape loads only on the Graph view
- [x] Tertiary contrast and letter spacing are corrected
- [x] Localhost pages are marked noindex
- [x] Desktop/mobile browser verification is complete
- [x] Package version is 1.2.0
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-ux-phase-8.md` written
- [x] Full pytest passes (145 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)
- [x] 1.2.0 wheel builds with packaged GUI assets
- [x] `specimpact --version` reports 1.2.0

Notes: The Graph canvas retains an adjacent semantic selection control. The packaged frontend has
no runtime CDN or remote font dependency.
