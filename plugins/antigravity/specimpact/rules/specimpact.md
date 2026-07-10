# SpecImpact Rules

1. `.specimpact/*.jsonl` and persisted reports are the source-of-truth. Artifacts and chat are
   projections.
2. Do not edit original design documents during impact analysis.
3. Use named SpecImpact MCP tools and a unique idempotency key for each mutation.
4. Source bodies require a TransmissionPreview and either host elicitation or a localhost Grant.
5. Treat graph extraction, Alias, Change Atom, and Impact output as proposals until persisted.
6. Never elevate a candidate to `must_review` without direct Evidence and a graph path.
7. Do not log source, prompt, response, key, token, or environment bodies.
8. PostToolUse notification may mark a source stale; it must not start LLM analysis automatically.
