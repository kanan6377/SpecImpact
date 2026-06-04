# SpecImpact

Evidence-backed design change impact review for software teams.

SpecImpact reads design documents and a change request, builds a local knowledge graph, and proposes
review candidates with relation paths and quotes. It is a review assistant, not an automatic final
decision maker.

## Why

Design changes rarely touch one file. They hit APIs, screens, tables, validations, external
interfaces, and tests. SpecImpact makes that blast radius inspectable:

- local-first graph extraction
- evidence quotes with file and line numbers
- `must_review` / `should_review` / `may_review` candidates
- Graph Explorer for relation review
- optional LLM extraction and batch reranking
- privacy checks before external transmission

Japanese user manual: [docs/user_manual_ja.md](docs/user_manual_ja.md)

Local GUI manual: [docs/gui_manual_ja.md](docs/gui_manual_ja.md)

## Quickstart

```powershell
python -m pip install -e .
specimpact init
specimpact ingest ./examples/credit_card_enrollment/docs --aliases ./examples/credit_card_enrollment/aliases.yml
specimpact analyze ./examples/credit_card_enrollment/changes/change_credit_limit.md
specimpact report --format markdown
specimpact why "カード入会申込API"
```

Local state is stored under `.specimpact/`.

## Optional Local GUI

```powershell
python -m pip install -e ".[gui]"
specimpact gui
```

Useful options:

```powershell
specimpact gui --port 8765
specimpact gui --project C:\work\my-system-impact
specimpact gui --no-open-browser
```

The GUI binds only to `127.0.0.1`. It has no LAN exposure option. Registered projects remain
independent local workspaces. The guided sample copies `examples/credit_card_enrollment` before it
runs, so the original sample is not modified.

The GUI is built as a local impact lab:

- Dashboard launchpad with graph counts, privacy status, LLM mode, and job history
- Guided demo
- Ingest for Markdown, OpenAPI, DDL, CSV, Excel, and managed uploads
- Analyze / Report with evidence and LLM advisory reasons
- Graph Explorer with relation status updates
- Settings for local backend, embeddings, OpenAI, Ollama, Codex CLI, and fake providers

## Extraction Model

Markdown extraction is convention-based and inspectable. Headings such as `API:`, `Screen:`,
`Table:`, `ValidationRule:`, and `ExternalIF:` define artifacts. Sections such as `Request fields`,
`Reads`, `Writes`, `Displays`, `Sends`, and `Covers` define relations. Plain text matches are kept
as conservative mentions.

Structured loaders cover straightforward OpenAPI, DDL, CSV, and Excel definitions. See
[docs/structured_loaders.md](docs/structured_loaders.md).

## Optional AI

Rule extraction remains the default. Optional LLM extraction and semantic retrieval can be enabled
independently:

```powershell
specimpact llm configure --provider openai --model <model>
specimpact llm configure --provider ollama --model <model> --base-url http://localhost:11434
specimpact llm configure --provider codex --model default
specimpact llm status
specimpact llm disable
specimpact embeddings rebuild --provider local
specimpact analyze ./change.md --no-llm
```

OpenAI, Codex CLI, remote Ollama, and OpenAI embeddings require per-command confirmation or `--yes`.
The Codex provider invokes a logged-in `codex exec` subprocess with an ephemeral session, an empty
temporary working directory, a read-only sandbox, and batched reranking. Localhost Ollama and local
embeddings stay on the machine. OpenAI API keys are read only from `OPENAI_API_KEY`.

## Review Workflow

```powershell
specimpact aliases suggest
specimpact aliases list
specimpact relations list
specimpact relations set-status rel.api.card_application.submit.request_field confirmed
specimpact inspect graph
specimpact inspect evidence ev.api.card_application.submit.request_field
specimpact why-not "本人確認サービス"
specimpact doctor --privacy
```

`why` and `why-not` are backed by the latest run's `trace.jsonl`. Evaluation metrics assist review
quality checks; they are not confidence scores.

## Optional Integrations

```powershell
specimpact backend set neo4j --uri bolt://localhost:7687
specimpact export-obsidian ./vault
specimpact review import ./examples/credit_card_enrollment/reviews/change_credit_limit.review.json
specimpact baseline create before
specimpact graph diff before
specimpact backend set local
```

The local JSONL backend remains the default. See [docs/integrations.md](docs/integrations.md).

## Development

```powershell
pytest -q
ruff check .
python -m compileall -q specimpact
specimpact release-check ./examples/evaluation/release_cases.yml
```

See [docs/roadmap.md](docs/roadmap.md), [docs/phase_status.md](docs/phase_status.md), and
[docs/release.md](docs/release.md).

## Before Public Publication

- Replace placeholder repository URLs in `pyproject.toml`.
- Add a real maintainer security contact in `SECURITY.md`.
- Confirm the synthetic sample data is acceptable for public release.
- Re-run the development checks above from a clean environment.

