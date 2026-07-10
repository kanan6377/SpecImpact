# Cursor Integration

## Install Runtime

The Cursor Plugin does not bundle Python or SpecImpact. Install the runtime first:

```powershell
uv tool install "specimpact[mcp,gui]"
# or
pipx install "specimpact[mcp,gui]"

cd C:\work\my-system-impact
specimpact init
specimpact agent doctor --host cursor --project .
```

For repository development, `python -m pip install -e ".[mcp,gui]"` is equivalent.

## Install Plugin

Add this repository's `plugins/cursor` directory as a Cursor Marketplace repository and install the
`specimpact` plugin. The package contains `.cursor-plugin/plugin.json`, four Skills, four Commands,
Rules, Hooks, and the stdio MCP configuration.

The MCP process is launched per workspace as:

```text
specimpact mcp --stdio --project ${workspaceFolder}
```

It sets `SPECIMPACT_HOST=cursor`. The package does not claim MCP sampling capability; Cursor uses
the prepare/submit Skill route unless sampling is explicitly available in a future host version.

## Workflows

- `/specimpact-onboard`: initialize, ingest, poll Jobs, and review Dirty Excel Regions
- `/specimpact-ingest`: ingest selected sources and submit host Region proposals
- `/specimpact-change`: turn natural language into Change Atoms and verified impacts
- `/specimpact-review`: review Evidence and persist status changes

The Commands and Skills invoke named MCP tools. They never call a generic action dispatcher and
never edit design originals.

## Canvas

The package includes three Markdown references:

- Impact Review
- Evidence / Graph
- Unified Review Queue

Cursor's stable public Plugin API does not currently register a custom persistent Canvas type.
The Skill therefore uses these references to generate a Canvas when supported and ordinary
Markdown otherwise. Canvas content is a projection. `.specimpact/*.jsonl` remains the source of
truth for Change, Impact Decision, Proposal, Alias, and relation status.

## Privacy

Source and Evidence MCP Resources contain metadata only. Content is returned through an
approval-gated tool. Cursor must show the MCP elicitation before SpecImpact consumes the one-time
Grant. Hooks must not log prompt text, source text, response text, environment values, or tokens.
