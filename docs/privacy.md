# Privacy

SpecImpact defaults to the local JSONL backend. Document chunks remain on the local machine.
No external LLM provider is configured or called. Use `specimpact doctor --privacy` to inspect
the active defaults.

Default mode:

```text
LLM: disabled
External transmission: none
Backend: local JSONL
Embeddings: local unless explicitly rebuilt with a remote provider
```

The doctor parses `config.yml` and treats only the exact `backend: local` value as the local
backend.

Optional OpenAI, Codex CLI, and remote Ollama calls require per-command confirmation or `--yes`.
The Codex provider sends only the requested extraction or batched candidate-reranking payload
through the logged-in `codex exec` subprocess. It uses an ephemeral session, an empty temporary
working directory, and a read-only sandbox. Localhost Ollama and local embeddings do not require
external transmission approval.
OpenAI API keys are read only from `OPENAI_API_KEY`.

The first local embedding rebuild may download the configured sentence-transformers model if it
is not already present in the local model cache. The design-document chunks are not sent as part
of that model download. Install and cache the model ahead of time for offline environments.

LLM trace rows store provider, model, purpose, timestamps, hashes, and minimal ID summaries. They
do not store document bodies, prompt text, raw provider responses, evidence quotes, LLM reasons,
or API keys.
