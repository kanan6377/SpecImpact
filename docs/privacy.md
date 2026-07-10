# Privacy

SpecImpact defaults to the local JSONL backend. Starting the CLI or Admin Console does not call an
external LLM. An Agent host receives source content only through an approval-gated MCP tool. Use
`specimpact doctor --privacy` and `specimpact agent doctor` to inspect the active runtime.

Default mode:

```text
LLM: disabled
Host LLM: available only through MCP approval
External transmission: none
Backend: local JSONL
Embeddings: local unless explicitly rebuilt with a remote provider
```

The doctor parses `config.yml` and treats only the exact `backend: local` value as the local
backend.

Host LLM is the standard workflow. Before content is returned to Cursor or Antigravity, SpecImpact
creates a metadata-only TransmissionPreview containing host, provider/model when known, purpose,
item count, redaction state, source hash, Evidence IDs, and expiry. External transmission requires
MCP elicitation or a localhost-issued ApprovalGrant.

The Grant is bound to project, purpose, and source hash, expires after ten minutes, and is consumed
once. Only its SHA-256 token hash is stored. `approved=true` is not an authorization mechanism.
For hosts without elicitation, the localhost approval page returns the plaintext token once; it is
then passed to `authorize_prepared_context` or `open_evidence`.

OpenAI, Codex CLI, and remote Ollama calls remain provider fallbacks and require per-command
confirmation or `--yes`.
The Codex provider sends only the requested extraction or batched candidate-reranking payload
through the logged-in `codex exec` subprocess. It uses an ephemeral session, an empty temporary
working directory, and a read-only sandbox. Localhost Ollama and local embeddings do not require
external transmission approval.
OpenAI API keys are read only from `OPENAI_API_KEY`.

The first local embedding rebuild may download the configured sentence-transformers model if it
is not already present in the local model cache. The design-document chunks are not sent as part
of that model download. Install and cache the model ahead of time for offline environments.

LLM trace rows store host/provider, model, purpose, timestamps, hashes, Evidence IDs, and minimal summaries. They
do not store document bodies, prompt text, raw provider responses, evidence quotes, LLM reasons,
or API keys.

Before an external provider call, payload redaction covers email addresses, phone numbers, URLs,
API-key-like values, long numeric identifiers, and labeled person, customer, member, and account
identifiers. The GUI audit endpoint applies a second allowlist and returns only transmission
metadata. Redaction reduces accidental disclosure risk but does not replace the required external
transmission preview and explicit approval.

MCP Source and Evidence Resources expose address/graph metadata only. Source rows, cell values,
rendered Regions, and Evidence quotes are returned through approval-gated tools. Workspace paths
are resolved before use; outside-root paths and symlink escapes are rejected.

Agent Hooks receive tool payloads but persist only workspace-relative path, source hash, host, and
time. They do not persist content, call an LLM, or automatically run impact analysis.
