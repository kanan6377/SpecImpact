# Agent Host Architecture

## Specification kernel boundary

All existing report-producing paths additionally call `semantic/service.py`, which captures
normalized ingestion state and invokes one bounded kernel. SQLite owns immutable analysis
snapshots, results and decision events; JSONL remains the legacy ingestion and compatibility
surface shown below. `specimpact.locking` supplies a common reentrant process lock without
depending on Application imports. See [the kernel contract](specification_kernel.md) for current
rules, normalized-source retention, transport behavior and migration limits.

## Runtime Boundaries

```mermaid
flowchart TB
    subgraph Host["Agent Host"]
        Cursor["Cursor Plugin<br/>Skills・Rules・Commands・Canvas"]
        AG["Antigravity Plugin<br/>Skills・Rules・Hooks・Artifacts"]
    end

    Cursor --> MCP
    AG --> MCP
    MCP["SpecImpact MCP stdio<br/>typed Tools・Resources・Prompts"] --> Approval["Privacy Gate<br/>Preview・Elicitation・One-time Grant"]
    Approval --> App["Application Service<br/>Command / Query"]
    CLI["CLI"] --> App
    Admin["localhost Admin Console"] --> App

    App --> Evidence["Evidence Graph<br/>Workbook・Sheet・Cell・Quote"]
    App --> Domain["Domain Graph<br/>Artifact・Entity・Relation"]
    App --> Impact["Impact Graph<br/>Change・Hypothesis・Decision"]
    Evidence --> Verify["Evidence Verifier"]
    Domain --> Verify
    Verify --> Impact
    Evidence --> JSONL[".specimpact local JSONL"]
    Domain --> JSONL
    Impact --> JSONL
    JSONL --> Obsidian["Obsidian projection"]
```

MCP, CLI, and Web do not own separate domain logic. They call the same Application layer. Cursor
Canvas, Antigravity Artifact, Admin Console, reports, and Obsidian are replaceable projections.

## Host Change Sequence

```mermaid
sequenceDiagram
    actor User
    participant Agent as Host Agent
    participant MCP as SpecImpact MCP
    participant Privacy as Privacy Gate
    participant Verify as Verifier
    participant Store as JSONL

    User->>Agent: Natural-language change
    Agent->>MCP: prepare_change
    MCP->>Privacy: hash + redaction preview
    Privacy-->>User: Elicitation or localhost approval
    User-->>Privacy: One-time approval
    MCP-->>Agent: Redacted context + Change Atom schema
    Agent->>MCP: submit_change_atoms
    MCP->>Store: Proposed Change Atoms
    Agent->>MCP: prepare_impact_context
    MCP-->>Agent: Candidate subgraphs + Evidence IDs
    Agent->>MCP: submit_impact_hypotheses
    MCP->>Verify: Validate Evidence, path, property, before value
    Verify->>Store: Verified report + Change Session
    User->>MCP: set_impact_decision
    MCP->>Store: Human status
```

## Status Ownership

```mermaid
stateDiagram-v2
    [*] --> unreviewed
    unreviewed --> accepted
    unreviewed --> rejected
    unreviewed --> needs_investigation
    needs_investigation --> accepted
    needs_investigation --> rejected
    accepted --> implemented
    implemented --> tested
    tested --> closed
```

Only an explicit human action changes Impact Decision status. `must_review` is a verifier-backed
review priority, not a decision state.

## Concurrency And Recovery

- `.specimpact/write.lock` serializes cross-process mutations.
- hashed idempotency keys replay completed mutations without running them twice.
- `.specimpact/jobs.jsonl` survives host restarts; queued/running records become interrupted.
- source hash changes generate graph diff and stale review records.
- MCP Tasks are not required; durable Job tools are the stable compatibility layer.
