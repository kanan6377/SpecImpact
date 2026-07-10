# SpecImpact Antigravity Plugin

This package bundles the SpecImpact MCP configuration, four Skills, Rules, a notification-only
PostToolUse Hook, and three Artifact templates. It does not bundle Python.

Install the runtime first:

```powershell
uv tool install "specimpact[mcp,gui]"
specimpact agent doctor --host antigravity --project C:\work\my-system
```

Install this directory into `.agents/plugins/specimpact` for one workspace or
`~/.gemini/config/plugins/specimpact` globally. The scripts beside this directory perform those
copies. See `docs/antigravity.md` in the repository.

The Hook records only workspace-relative path, source hash, host, and time. It never starts an LLM
call or external transmission.
