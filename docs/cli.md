# Stable CLI v1.0

Core workflow: `init`, `ingest`, `analyze`, `report`, `why`, `why-not`, `status`,
`doctor --privacy`, and `eval`.

Review workflow: `aliases`, `inspect`, `relations`, `review import`, `baseline create`, and
`graph diff`.

Loaders: `ingest-openapi`, `ingest-ddl`, `ingest-csv`, and `ingest-excel`.

Optional integration: `backend set` and `export-obsidian`.

Optional LLM integration: `llm configure --provider openai|ollama|codex|fake --model <model>`.
The `codex` provider invokes a logged-in Codex CLI subprocess and requires external transmission
approval for each command. Analyze uses LLM change extraction plus batched candidate reranking,
so Codex is not invoked once per candidate.

Release validation: `release-check <dataset-manifest>`.

Optional localhost GUI: `gui [--port 8765] [--project <directory>] [--no-open-browser]`.
Install it with `pip install -e ".[gui]"`. See [gui_manual_ja.md](gui_manual_ja.md).
