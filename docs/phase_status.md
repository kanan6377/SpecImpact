# Phase Status

## Specification kernel phase 5

Status: complete (engineering delivery); independent enterprise/user evaluation remains open

Golden source-to-analysis walkthrough, user/architecture/privacy/migration documentation,
distribution checks and Git delivery. Independent enterprise/user-time evaluation remains open.
Review: `docs/reviews/kernel-phase-5.md`.

Final checks: pytest 292 passed / 1 skipped; ruff and compileall passed; release-check 21 cases
passed; frontend TypeScript/build passed; wheel build and installed-wheel CLI walkthrough passed.
The typed rule scope is maximum length. No general enterprise accuracy or review-time claim.

## Specification kernel phase 4

Status: complete; pytest 288 passed / 1 skipped, ruff passed

Common CLI/Host/Application report analysis, operation-bound paginated Host submissions,
stale-context rejection, immutable review provenance and inspection/replay/exchange CLI.
Review: `docs/reviews/kernel-phase-4.md`.

## Specification kernel phase 3

Status: complete; pytest 280 passed / 1 skipped, ruff passed

Transactional SQLite analysis snapshots, immutable runs, replay/export/import and version-bound
decision events; process-locked capture. Review: `docs/reviews/kernel-phase-3.md`.

## Specification kernel phase 2

Status: complete; pytest 275 passed / 1 skipped, ruff passed

Bounded operation-scoped analysis, labelled length constraints, independent evidence strength,
coverage and adversarial regression cases. Review: `docs/reviews/kernel-phase-2.md`.

## Specification kernel phase 1

Status: complete; pytest 260 passed / 1 skipped, ruff passed

Typed source anchors, mentions, identity assertions, length specifications and change operations;
multi-change parsing and explicit character/byte units. Review: `docs/reviews/kernel-phase-1.md`.

## Specification kernel phase 0

Status: complete; pytest 249 passed / 1 skipped, ruff passed

Implementation contract and baseline frozen in `docs/specs/specification-kernel.md`.
Review: `docs/reviews/kernel-phase-0.md`. No future-phase implementation introduced.

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

## v1.2.0 Source Viewer UX

Scope:
- SharePoint-style inline source selection and preview
- source-list and in-document search
- Dirty Excel sheet and cell-address navigation
- responsive stacked viewer for narrow screens

Completion checklist:
- [x] Source selection opens the document without leaving the page
- [x] Selected source is persisted in the URL
- [x] Markdown/text rows and Dirty Excel cells remain evidence-highlighted
- [x] Dirty Excel sheets can be selected in the viewer
- [x] Desktop and mobile layouts are responsive
- [x] README and manuals updated
- [x] `docs/reviews/v1.2.0-source-viewer.md` written

Notes: This is a cell-addressed evidence viewer, not an Office-compatible workbook renderer. Images,
shapes, formulas as rendered values, and workbook editing remain outside the current scope.

## v1.3.0 Agent Host Phase 1

Status: complete

Scope:
- UI-independent Application Service extraction
- shared Pydantic public contracts and JSON Schema generation
- CLI/Web service compatibility boundary
- project model ownership moved out of Web UI

Completion checklist:
- [x] Existing Web imports and output remain compatible
- [x] Application facade covers current command/query services
- [x] Public contract serialization tests pass
- [x] README architecture updated
- [x] `docs/reviews/v1.3.0-agent-host-phase-1.md` written
- [x] Full pytest passes (149 tests)
- [x] Full ruff check passes
- [x] compileall passes
- [x] No MCP or host-plugin implementation leaked into Phase 1

Notes: This phase changes internal ownership only. MCP transport, durable jobs, host LLM workflows,
and host packages are gated to later Agent Host phases.

## v1.3.0 Agent Host Phase 2

Status: complete

Scope:
- MCP 1.x stdio server with typed tools, resources, and prompts
- workspace and symlink boundary enforcement
- canonical durable jobs with legacy GUI-ledger migration
- cross-process mutation lock and idempotency ledger
- metadata-only transmission preview and scoped one-time approval grant
- REST/MCP shared contract schema endpoint

Completion checklist:
- [x] Generic execute tool is not exposed
- [x] Source and graph resources are bounded and cursor-paginated
- [x] Unknown IDs and uninitialized projects are rejected safely
- [x] Mutation idempotency and process locking are tested
- [x] Legacy job history is copied without deletion
- [x] Grant expiry, project/purpose/source binding, and token reuse are tested
- [x] README, CLI reference, and MCP guide updated
- [x] `docs/reviews/v1.3.0-agent-host-phase-2.md` written
- [x] Full pytest passes (160 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes

Notes: Durable Job tools are the compatibility baseline. The deprecated MCP Tasks extension is not
advertised. Host sampling and prepare/submit analysis remain Phase 3. The skipped test is the
Windows symlink-escape case when the current account cannot create symbolic links.

## v1.3.0 Agent Host Phase 3

Status: complete

Scope:
- HostSamplingAdapter for MCP sampling
- host Dirty Excel Region extraction and verified Graph Proposal submission
- approval-gated Change Atom and impact prepare/submit workflows
- host output schemas and verifier-enforced persistence
- host audit hashes and schema-violation metadata
- host sampling, Skill, configured-provider, heuristic route selection
- shared report/session persistence for CLI and host analysis

Completion checklist:
- [x] External payload is withheld until a scoped Grant is consumed
- [x] Host sampling validates structured JSON and redacts payloads
- [x] Invalid schema, Evidence, node, relation, and before values are rejected
- [x] LLM-only `must_review` cannot bypass the verifier
- [x] Retry returns the persisted idempotent result
- [x] Sampling interruption and non-text responses fail without body leakage
- [x] Host route works without a configured SpecImpact provider
- [x] README, MCP guide, and Host LLM guide updated
- [x] `docs/reviews/v1.3.0-agent-host-phase-3.md` written
- [x] Full pytest passes (178 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes

Notes: Host-generated data remains proposal/hypothesis data. JSONL Change Sessions and verified
reports are authoritative; host chat, Canvas, and Artifacts are projections.

## v1.3.0 Agent Host Phase 4

Status: complete

Scope:
- Cursor Marketplace and Plugin manifests
- MCP configuration, four Skills, Rules, Commands, and privacy-safe Hook
- Impact Review, Evidence Graph, and Unified Review Queue Canvas references
- Agent runtime doctor and hash-only source-change notification
- Cursor installation and privacy manual

Completion checklist:
- [x] Official Cursor plugin and marketplace schemas validate
- [x] Plugin starts the workspace-scoped stdio MCP server
- [x] Four Skills map to onboarding, ingest, change, and review
- [x] Three Canvas references retain JSONL as source-of-truth
- [x] Plugin contains no Python runtime
- [x] Hook stores path/hash metadata only and starts no LLM work
- [x] `specimpact agent doctor --host cursor` is available
- [x] README and Cursor manual updated
- [x] `docs/reviews/v1.3.0-agent-host-phase-4.md` written
- [x] Full pytest passes (188 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes

Notes: Canvas is generated through a Skill reference because Cursor does not expose a stable public
API for registering a custom persistent Canvas type. Markdown is the fallback projection.

## v1.3.0 Agent Host Phase 5

Status: complete

Scope:
- Antigravity workspace/global Plugin package
- MCP config, four Skills, Rules, and PostToolUse Hook
- three review Artifact templates
- localhost approval page and one-time token fallback
- parallel-subagent consolidation rules
- Antigravity installation and privacy manual

Completion checklist:
- [x] Workspace and global install scripts are included
- [x] Plugin contains no Python runtime
- [x] Four Skills use the same typed MCP contracts
- [x] Hook detects Agent write tools and starts no LLM work
- [x] Three Artifact templates retain JSONL as source-of-truth
- [x] Non-elicitation hosts can use localhost approval and `authorize_prepared_context`
- [x] Parallel investigation converges on one verifier and Change Session
- [x] README and Antigravity manual updated
- [x] `docs/reviews/v1.3.0-agent-host-phase-5.md` written
- [x] Full pytest passes (196 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes

Notes: The Hook covers Antigravity Agent write tools, not arbitrary filesystem changes. Existing
source freshness detects other changes during re-ingestion.

## v1.3.0 Agent Host Phase 6

Status: complete

Scope:
- Agent-host-first README and GitHub presentation
- architecture, Host LLM, Cursor, Antigravity, Privacy, and demo manuals
- Admin Console terminology and CLI/manual alignment
- v1.3 version metadata and Changelog
- GitHub Actions, Issue forms, and PR template

Completion checklist:
- [x] README makes Cursor the standard front and Admin Console the management surface
- [x] Architecture and sequence diagrams show trust/state boundaries
- [x] Cursor/Antigravity installation and approval fallback are documented
- [x] Privacy manual covers metadata-only Resources and one-time Grants
- [x] Dirty Excel benchmark has an Agent Host walkthrough
- [x] README links and release versions are tested
- [x] GitHub CI covers Python, frontend, benchmark, and wheel
- [x] `docs/reviews/v1.3.0-agent-host-phase-6.md` written
- [x] Full pytest passes (199 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes

Notes: Mermaid is used for GitHub-native diagrams. Existing GUI screenshots now represent the
Admin Console rather than the primary daily interaction surface.

## v1.3.0 Agent Host Phase 7

Status: complete

Scope:
- Dirty SIer workbook classification hardening
- external interface benchmark workbook
- end-to-end Host LLM change and review flow
- real MCP stdio and distribution verification
- final release quality gates

Completion checklist:
- [x] Embedded revision history no longer masks DB mapping sheets
- [x] Validation tables containing screen terms remain validation regions
- [x] External IF workbook contributes an Evidence-backed graph artifact
- [x] Natural-language credit-limit change retrieves Screen, Validation, API, DB, External IF,
  and Test impacts
- [x] Host submission is verifier-checked and persisted in one Change Session
- [x] Impact decision is visible through Application Service and Obsidian export
- [x] Real MCP stdio handshake lists typed Tools, Resources, and four Prompts
- [x] Cursor and Antigravity package manifests validate
- [x] Frontend check/build and wheel build pass
- [x] `docs/reviews/v1.3.0-agent-host-phase-7.md` written
- [x] Full pytest passes (206 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes
- [x] release-check passes (21 cases)

Notes: The skipped Windows symlink test is limited to accounts without symbolic-link privileges.
SharePoint/Microsoft Graph, NotebookLM Enterprise, M365 Copilot remote MCP, and a VS Code custom
editor remain explicitly outside v1.3.0.

## Fintan Compatibility Experiment

Status: complete

Scope:
- Fixed-commit Fintan public design-workbook fetch without vendoring the source files
- 21-workbook project-name 128→256 compatibility baseline
- Dirty Excel classification, Evidence Graph, deterministic evaluation, and HostWorkflow semantic round trip
- Provenance SHA-256, one-time external approval, Host hypothesis submission, and verifier result documentation

Completion checklist:
- [x] 21 selected Workbook sources and Fintan license/attribution are documented
- [x] Fixed commit and SHA-256 provenance approach are documented
- [x] Deterministic acceptance gates and final measurements are documented
- [x] Initial boundary-anchor failure and remediation are documented
- [x] Host LLM preview, one-time grant, audit, and verifier outcomes are documented
- [x] `docs/reviews/fintan-compatibility-benchmark.md` written
- [x] README, CLI, Japanese user manual, example guide, and CHANGELOG updated
- [x] Full pytest passes (249 passed, 1 skipped)
- [x] Full ruff check passes
- [x] compileall passes
- [x] Release-check passes (21 cases)
- [x] Focused Fintan regression suite passes
- [x] Scope and future-phase leakage checks documented

Results: 19/19 expected workbooks, zero false positives, 20/20 Evidence anchors, 100% Evidence and
cell-address coverage, 0% unknown sheets, and 40 visible candidates. Host submission produced 33
`must_review` and 7 `should_review` results after verifier assessment.

Known limitations: 12 sheets contain unsupported drawings/images, one unresolved mention remains,
and visual semantics are not analyzed. The real-corpus Host semantic round trip used direct
HostWorkflow; MCP stdio is covered by existing handshake/tests and was not used to submit this
Corpus.

Future-phase leakage check: no automatic design-document editing, Neo4j requirement, new Web UI,
Excel/PDF/docx conversion, SharePoint/Microsoft Graph, NotebookLM, M365 Copilot remote MCP, or
VS Code custom editor was introduced.





