# SpecImpact UX Redesign Plan

## Product Direction

SpecImpact is being redesigned from a prototype dashboard into an evidence review workspace.
The primary job is not viewing metrics. It is reviewing a proposed design change while keeping
the impact candidate, source document, graph path, evidence, and human decision in one context.

The redesign follows these principles:

1. Content first. Navigation and controls support the current review object.
2. One review context. Candidate, source, and evidence must remain synchronized.
3. Progressive disclosure. The default view stays concise; technical provenance is available in
   the inspector.
4. Familiar desktop patterns. Use a sidebar, content list, work surface, and optional inspector.
5. Evidence before decoration. Color communicates state and priority, not branding alone.
6. Local and inspectable. Provider, transmission, source freshness, and rule/LLM origin are visible.
7. Review assist. The interface never presents an LLM proposal as a final decision.

The visual language should borrow the clarity, hierarchy, restraint, and adaptive split-view
patterns associated with high-quality desktop tools. It must not copy proprietary Apple assets or
trade dress. SpecImpact uses its own tokens, Lucide-compatible iconography, and evidence-focused
interaction model.

## Current UX Audit

### Information Architecture

- The production template still describes itself as a prototype.
- Static demo content and live API data are mixed in the same runtime.
- Registered routes and visible views do not match consistently.
- Ingest, source inspection, proposal review, change analysis, and decision management are spread
  across disconnected surfaces.
- The selected design document is displayed in the change form but is not enforced as retrieval
  scope.

### Interaction

- Project switching, ingest, and provider configuration still contain mock-only actions.
- Alias, graph proposal, relation, and impact decision mutations exist in the backend but are not
  all available in the current console.
- Impact candidates and source evidence are displayed as separate modes instead of a persistent
  review split view.
- Loading, empty, failed, approval-required, and local-fallback states do not share one state model.
- The browser URL does not reliably preserve the selected view, filters, candidate, or source.

### Visual Design

- The dashboard gives static explanatory content too much space for an operational tool.
- Repeated cards weaken hierarchy and reduce scanability.
- Priority, review status, evidence strength, and provenance compete visually.
- The current interface depends on remote fonts and icon/chart CDNs despite the local-first model.
- Dense lists, source viewing, and graph inspection do not yet share stable pane dimensions.

### Trust And Review Safety

- The interface does not consistently distinguish rule output, LLM output, verifier output, and
  human decisions.
- Source freshness and stale decisions are not modeled in the current GUI.
- A rejected graph proposal does not transactionally remove or invalidate graph records derived
  from that proposal.
- Review progress is not tracked with a file/candidate viewed state.

## Target Information Architecture

The desktop application uses four stable regions:

```text
Navigation | Review list | Work surface | Evidence inspector
```

The inspector can collapse. On narrower windows, the review list and inspector become drawers.
The navigation hierarchy remains at two levels or fewer.

### Navigation

- Change Inbox
- Design Sources
- Knowledge Graph
- Review Queue
- Jobs and Audit
- Settings

### Change Review Workspace

The primary workflow is:

1. Select source scope.
2. Enter a natural-language change request.
3. Review and edit extracted Change Atoms.
4. Preview external transmission and start analysis.
5. Review candidates in priority order.
6. Open the exact source row or cell in the work surface.
7. Inspect graph path, alias chain, evidence, freshness, and generation origin.
8. Record a decision and reason.
9. Track implementation, testing, and closure.

The work surface supports synchronized tabs for source, proposed diff, and local graph. Changing
the selected impact updates all tabs without navigating away from the review.

### Design Sources

- Workbook/document list with ingest health and version.
- Sheet and region navigator.
- Search and evidence-addressable source viewer.
- Unsupported drawing and unresolved-reference inbox.
- Re-ingest and source-diff actions.

### Review Queue

One queue contains graph proposals, aliases, unresolved mentions, relation reviews, stale evidence,
and impact decisions. Saved views can filter by type, status, priority, source, and change request.

## Design System Requirements

- System-first font stack with no runtime font download.
- Twelve-column content grid and stable split-pane constraints.
- Four-pixel spacing base with an eight-pixel primary rhythm.
- Eight-pixel maximum card radius unless a native control requires otherwise.
- Neutral surfaces with semantic red, amber, blue, and green reserved for state.
- No decorative gradients, floating section cards, or nested cards.
- Toolbar actions are grouped by context and ordered by frequency.
- Icon-only controls use familiar symbols and tooltips.
- Every interactive state has visible focus, hover, pressed, disabled, busy, and error treatment.
- WCAG 2.2 AA contrast and keyboard navigation are release requirements.
- Reduced-motion mode disables nonessential motion.

## Frontend Architecture Decision

The recommended implementation is React, TypeScript, and Vite as a build-time frontend. FastAPI
remains the application and API host. Compiled static assets are packaged with the Python wheel, so
end users do not need Node.js.

The migration is justified by the amount of synchronized state required across projects, jobs,
sources, impacts, graph selection, review decisions, routing, and external approval. The existing
single-file console script is retained only until the corresponding production views have migrated.

Architecture constraints:

- No production mock-data fallback.
- No runtime CDN dependency.
- Typed API boundary.
- URL-addressable views and selections.
- A single query cache and explicit mutation invalidation.
- FastAPI security, project queue, and external-transmission approval remain authoritative.
- Cytoscape remains the graph renderer unless a measured limitation requires replacement.

## Measurement

The current interface is the baseline. The redesign is complete only when these outcomes are
verified:

- A reviewer can move from an impact candidate to exact source evidence in one action.
- The main change-review flow completes without leaving the workspace.
- Every candidate displays source, graph path, verifier result, generation origin, and review state.
- All production views are deep-linkable and preserve selection in the URL.
- There is no mock data, prototype ribbon, or inactive production control.
- Keyboard-only review is possible.
- Desktop layouts at 1280x720 and 1440x900 have no overlap or horizontal page scroll.
- Narrow layouts remain usable without hiding critical actions.
- Browser console errors and failed API requests are zero in the guided workflow.

## Delivery Phases

1. Frontend foundation and production-state cleanup.
2. Onboarding and Design Sources.
3. Change Review Workspace.
4. Unified Review Queue and transactional proposal decisions.
5. Source versioning, graph diff, and stale evidence propagation.
6. Private validation of new evidence-proof techniques before any public implementation.
7. Obsidian integration, accessibility, performance, documentation, and release validation.

Each phase receives its own review file and must pass `pytest -q`, `ruff check .`, compile checks,
and relevant browser verification before the next phase begins.

## Intellectual Property Boundary

General UX work, bug fixes, API wiring, source versioning, and review workflow improvements may be
developed in the public repository.

Potentially patent-sensitive algorithms must not be specified or implemented in the public
repository before an explicit filing decision. Prior to public work, maintain a private invention
record containing inventors, dates, technical problem, system diagrams, measurable technical
effect, alternatives, and prior-art comparison. Obtain qualified patent advice before deciding
whether and how the work should interact with the Apache-2.0 patent grant.

This document records process boundaries only. It intentionally does not disclose proposed claim
language or implementation details for a future invention.
