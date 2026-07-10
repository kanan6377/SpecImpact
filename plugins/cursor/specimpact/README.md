# SpecImpact Cursor Plugin

This package connects Cursor to the local SpecImpact MCP server. It contains Skills, Rules,
Commands, a privacy-safe source-change Hook, and three Canvas reference templates. It contains no
Python runtime.

Install SpecImpact first:

```powershell
uv tool install "specimpact[mcp,gui]"
specimpact agent doctor --host cursor --project C:\work\my-system
```

Then install this Plugin from the repository's `plugins/cursor` Marketplace. The Plugin starts
`specimpact mcp --stdio --project ${workspaceFolder}`. See the repository `docs/cursor.md` for the
workflow and privacy contract.

Licensed under Apache-2.0; see the repository root `LICENSE`.
