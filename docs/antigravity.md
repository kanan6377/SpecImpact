# Antigravity Integration

## Install Runtime

```powershell
uv tool install "specimpact[mcp,gui]"
cd C:\work\my-system-impact
specimpact init
specimpact agent doctor --host antigravity --project .
```

The Plugin does not bundle Python. Keep `specimpact` on PATH for the Antigravity process.

## Install Plugin

Workspace installation:

```powershell
.\plugins\antigravity\install-workspace.ps1 -Workspace C:\work\my-system-impact
```

This copies the package to `.agents/plugins/specimpact`. Global installation uses:

```powershell
.\plugins\antigravity\install-global.ps1
```

and targets `~/.gemini/config/plugins/specimpact`. Shell equivalents are included for macOS and
Linux.

## LLM And Approval

Antigravity uses the same MCP prepare/submit contracts as Cursor. The package does not declare
sampling or elicitation capabilities that are not guaranteed by the host.

When a `prepare_*` result is withheld:

1. Open its localhost `approval_url`.
2. Review host, purpose, item count, redaction state, source hash, and expiry.
3. Approve to receive a one-time token.
4. Call `authorize_prepared_context` with the context ID and token.
5. Submit the structured result normally.

The token is not persisted in plaintext and cannot be reused. `open_evidence` accepts the same
localhost-issued token fallback.

## Parallel Agents

Antigravity may investigate screen, validation, API, DB, external IF, and test candidates with
parallel subagents. Each subagent works only from the bounded PreparedContext. Their conclusions
must be consolidated into one `submit_impact_hypotheses` call, one Change Session, and one
SpecImpact verifier result.

## Hook Boundary

The PostToolUse Hook watches Antigravity's `write_to_file`, `replace_file_content`, and
`multi_replace_file_content` operations. It records only workspace-relative path, source hash,
host, and time. It does not call an LLM, send content, or run impact analysis.

The Hook is not an operating-system file watcher. Direct editor changes, sync clients, git
checkout, and external processes are detected later by normal source hash/freshness checks.

## Artifacts

Three Markdown templates are provided for Impact Review, Evidence Graph, and Unified Review Queue.
Antigravity currently has no documented Plugin API for registering a custom persistent Artifact
type, so Skills generate ordinary Markdown Artifacts. They are projections; local JSONL remains the
source-of-truth.
