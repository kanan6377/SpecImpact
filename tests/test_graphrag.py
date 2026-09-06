from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.config import load_config, save_config
from specimpact.core import (
    _apply_rerank_guardrails,
    analyze_change,
    ingest_documents,
    latest_run_dir,
)
from specimpact.embeddings import (
    EmbeddingRecord,
    FakeEmbeddingClient,
    _read_records,
    _write_records,
    rebuild_embeddings,
    semantic_search,
)
from specimpact.extraction import AliasCatalog, GraphRecords
from specimpact.graphrag import (
    ChangeExtraction,
    CodexCLIClient,
    FakeLLMClient,
    OllamaLLMClient,
    OpenAILLMClient,
    configure_llm,
    extract_graph_with_llm,
    is_loopback_url,
    llm_status,
    redact_payload,
)
from specimpact.loaders import load_document
from specimpact.models import Artifact, Chunk, Entity, Impact, Relation
from specimpact.store import LocalStore

runner = CliRunner()


def test_cli_reports_package_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "1.3.0"


def test_external_payload_redaction_covers_common_customer_identifiers() -> None:
    payload = {
        "text": (
            "氏名: 山田 太郎\n顧客番号: CUST-123456\n"
            "email=user@example.test phone=090-1234-5678\n"
            "url=https://example.test/customer/1 token=sk-1234567890"
        ),
        "account_number": "ABCD1234",
        "design_term": "requestedCreditLimit",
    }

    redacted = redact_payload(payload)

    serialized = json.dumps(redacted, ensure_ascii=False)
    for secret in (
        "山田 太郎",
        "CUST-123456",
        "user@example.test",
        "090-1234-5678",
        "https://example.test/customer/1",
        "sk-1234567890",
        "ABCD1234",
    ):
        assert secret not in serialized
    assert redacted["design_term"] == "requestedCreditLimit"
    assert serialized.count("[REDACTED]") >= 6


def test_external_payload_redaction_preserves_opaque_graph_ids() -> None:
    payload = {
        "evidence_ids": ["ev.1234567890", "ev.abcdef1234"],
        "relation_id": "rel.9876543210",
        "standalone_customer_number": "1234567890",
    }

    redacted = redact_payload(payload)

    assert redacted["evidence_ids"] == ["ev.1234567890", "ev.abcdef1234"]
    assert redacted["relation_id"] == "rel.9876543210"
    assert redacted["standalone_customer_number"] == "[REDACTED]"


def test_llm_config_status_and_loopback_detection(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    configure_llm(store, "ollama", "qwen-test", "http://localhost:11434")
    assert llm_status(store)["external_transmission"] is False
    configure_llm(store, "ollama", "qwen-test", "https://ollama.example.test")
    assert llm_status(store)["external_transmission"] is True
    assert is_loopback_url("http://127.0.0.1:11434")
    assert is_loopback_url("http://[::1]:11434")
    assert not is_loopback_url("https://ollama.example.test")
    configure_llm(store, "codex", "gpt-test")
    assert llm_status(store)["external_transmission"] is True


def test_codex_cli_structured_uses_ephemeral_read_only_schema_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"changed_entities": []}', encoding="utf-8")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("specimpact.graphrag.subprocess.run", fake_run)
    result = CodexCLIClient("gpt-test", executable="codex.cmd").structured(
        "change_extraction",
        {"text": "SECRET_CHANGE_BODY"},
        ChangeExtraction,
    )

    command, kwargs = calls[0]
    assert result.changed_entities == []
    assert command[:2] == ["codex.cmd", "exec"]
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "SECRET_CHANGE_BODY" not in " ".join(command)
    assert b"SECRET_CHANGE_BODY" in kwargs["input"]


def test_codex_cli_default_model_uses_cli_default(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text('{"changed_entities": []}', encoding="utf-8")

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("specimpact.graphrag.subprocess.run", fake_run)
    CodexCLIClient("default", executable="codex.cmd").structured(
        "change_extraction",
        {"text": "change"},
        ChangeExtraction,
    )

    assert "--model" not in commands[0]


def test_llm_ingest_relation_is_unconfirmed_inferred_semantic(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Notes\n\nThe screen displays amount.\n", encoding="utf-8")
    chunk_id = load_document(docs / "notes.md", source_key="notes.md")[2][0].chunk_id
    client = FakeLLMClient(
        {
            "ingest_extraction": {
                "chunk_id": chunk_id,
                "artifacts": [{"display_name": "Payment Screen", "artifact_type": "Screen"}],
                "entities": [{"display_name": "amount"}],
                "relations": [
                    {
                        "source_name": "Payment Screen",
                        "source_type": "Screen",
                        "target_name": "amount",
                        "relation_type": "DISPLAYS",
                        "evidence_quote": "The screen displays amount.",
                        "line_start": 3,
                        "line_end": 3,
                    }
                ],
            }
        }
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs, llm_client=client)
    relation = next(
        item for item in store.read("relations", Relation) if item.extraction_method == "llm"
    )
    assert (relation.status, relation.polarity, relation.match_type) == (
        "unconfirmed",
        "inferred",
        "semantic",
    )


def test_llm_failure_rolls_back_graph_and_manifest(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text("# API: Stable\n", encoding="utf-8")
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs)
    before = _snapshot(store)

    class FailingClient(FakeLLMClient):
        def structured(self, purpose, payload, schema):
            raise ValueError("invalid structured output")

    with pytest.raises(ValueError, match="invalid structured output"):
        ingest_documents(store, docs, llm_client=FailingClient())
    assert _snapshot(store) == before


def test_unknown_llm_change_entity_is_trace_suggestion_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(
        "# API: Payment\n\n## Request fields\n- amount\n",
        encoding="utf-8",
    )
    change = tmp_path / "change.md"
    change.write_text("# Add settlement code\n\nUpdate settlementCode.\n", encoding="utf-8")
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs)
    client = FakeLLMClient(
        {
            "change_extraction": {
                "changed_entities": [
                    {
                        "name": "settlementCode",
                        "reason": "Named in the change request.",
                    }
                ]
            }
        }
    )
    analyze_change(store, change, llm_client=client)
    entities = {item.display_name for item in store.read("entities", Entity)}
    assert "settlementCode" not in entities
    lines = (latest_run_dir(store) / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    suggestion = first["changed_entity_suggestions"][0]
    assert suggestion["name_hash"] == hashlib.sha256(b"settlementCode").hexdigest()
    assert "settlementCode" not in json.dumps(first)


def test_embedding_rebuild_is_incremental_prunes_and_searches_top_k(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    store.write(
        "chunks",
        [
            _chunk("chunk.a", "alpha"),
            _chunk("chunk.b", "beta"),
            _chunk("chunk.c", "gamma"),
        ],
    )
    client = FakeEmbeddingClient(
        {
            "alpha": [1.0, 0.0],
            "beta": [0.8, 0.2],
            "gamma": [0.0, 1.0],
            "query": [1.0, 0.0],
        }
    )
    assert rebuild_embeddings(store, provider="fake", client=client) == 3
    assert rebuild_embeddings(store, provider="fake", client=client) == 0
    trace = (store.root / "trace.jsonl").read_text(encoding="utf-8")
    assert '"purpose": "embeddings_rebuild"' in trace
    assert '"vector"' not in trace
    assert semantic_search(store, "query", top_k=2, client=client) == [
        ("chunk.a", 1.0),
        ("chunk.b", pytest.approx(0.9701425)),
    ]
    store.write("chunks", [_chunk("chunk.a", "alpha changed"), _chunk("chunk.c", "gamma")])
    assert rebuild_embeddings(store, provider="fake", client=client) == 1
    assert {item.chunk_id for item in _read_records(store)} == {"chunk.a", "chunk.c"}


def test_openai_embeddings_require_an_explicit_model(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    with pytest.raises(ValueError, match="embedding model is required"):
        rebuild_embeddings(store, provider="openai", yes=True)


def test_openai_semantic_query_requires_confirmation(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    config = load_config(store)
    config["embeddings"] = {
        "enabled": True,
        "provider": "openai",
        "model": "embedding-test-model",
    }
    save_config(store, config)
    store.write("chunks", [_chunk("chunk.a", "alpha")])
    _write_records(
        store,
        [
            EmbeddingRecord(
                chunk_id="chunk.a",
                content_hash="hash",
                provider="openai",
                model="embedding-test-model",
                vector=[1.0, 0.0],
            )
        ],
    )
    client = _RecordingEmbeddingClient(
        provider="openai",
        model="embedding-test-model",
        vectors={"query": [1.0, 0.0]},
    )
    with pytest.raises(ValueError, match="External transmission was not approved"):
        semantic_search(store, "query", top_k=1, client=client)
    assert semantic_search(
        store,
        "query",
        top_k=1,
        client=client,
        confirm=lambda _message: True,
    ) == [("chunk.a", 1.0)]


def test_embedding_external_client_cannot_bypass_local_provider_consent(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    store.write("chunks", [_chunk("chunk.secret", "SECRET_DOCUMENT")])
    client = _RecordingEmbeddingClient(
        provider="openai",
        model="intfloat/multilingual-e5-small",
    )
    with pytest.raises(ValueError, match="must match"):
        rebuild_embeddings(store, provider="local", client=client)
    assert client.document_calls == []

    config = load_config(store)
    config["embeddings"] = {
        "enabled": True,
        "provider": "local",
        "model": "intfloat/multilingual-e5-small",
    }
    save_config(store, config)
    _write_records(
        store,
        [
            EmbeddingRecord(
                chunk_id="chunk.secret",
                content_hash="hash",
                provider="local",
                model="intfloat/multilingual-e5-small",
                vector=[1.0, 0.0],
            )
        ],
    )
    with pytest.raises(ValueError, match="must match"):
        semantic_search(store, "SECRET_QUERY", top_k=1, client=client)
    assert client.query_calls == []


def test_llm_standalone_nodes_are_not_saved(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("# Notes\n", encoding="utf-8")
    chunk_id = load_document(docs / "notes.md", source_key="notes.md")[2][0].chunk_id
    client = FakeLLMClient(
        {
            "ingest_extraction": {
                "chunk_id": chunk_id,
                "artifacts": [{"display_name": "Ghost API", "artifact_type": "API"}],
                "entities": [{"display_name": "ghostField"}],
                "relations": [],
            }
        }
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs, llm_client=client)
    assert store.read("artifacts", Artifact) == []
    assert store.read("entities", Entity) == []


def test_llm_only_entity_does_not_become_rule_direct_must_review(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "notes.md"
    source.write_text("# Notes\n\nPayment uses ghostField.\n", encoding="utf-8")
    chunk_id = load_document(source, source_key="notes.md")[2][0].chunk_id
    ingest_client = FakeLLMClient(
        {
            "ingest_extraction": {
                "chunk_id": chunk_id,
                "artifacts": [],
                "entities": [],
                "relations": [
                    {
                        "source_name": "Payment API",
                        "source_type": "API",
                        "target_name": "ghostField",
                        "relation_type": "REQUEST_FIELD",
                        "evidence_quote": "Payment uses ghostField.",
                        "line_start": 99,
                        "line_end": 99,
                    }
                ],
            }
        }
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs, llm_client=ingest_client)
    change = tmp_path / "change.md"
    change.write_text("# Update\n\nghostField\n", encoding="utf-8")
    analyze_client = FakeLLMClient(
        {
            "change_extraction": {
                "changed_entities": [
                    {
                        "entity_id": "entity.ghostfield",
                        "name": "ghostField",
                        "reason": "Referenced.",
                    }
                ]
            }
        }
    )
    report = analyze_change(store, change, llm_client=analyze_client)
    direct = next(item for item in report.impacts if item.artifact_id == "entity.ghostfield")
    assert direct.review_priority == "may_review"
    assert direct.rule_assessment == "inferred_relation"


def test_llm_quote_must_be_non_empty_unique_and_line_is_derived(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nunique quote\n\nrepeat\nrepeat\n", encoding="utf-8")
    document, sections, chunks = load_document(source, source_key="notes.md")
    extraction = {
        "chunk_id": chunks[0].chunk_id,
        "artifacts": [],
        "entities": [],
        "relations": [
            {
                "source_name": "Unique API",
                "source_type": "API",
                "target_name": "uniqueField",
                "relation_type": "REQUEST_FIELD",
                "evidence_quote": "unique quote",
                "line_start": 999,
                "line_end": 999,
            },
            {
                "source_name": "Blank API",
                "source_type": "API",
                "target_name": "blankField",
                "relation_type": "REQUEST_FIELD",
                "evidence_quote": " ",
                "line_start": 1,
                "line_end": 1,
            },
            {
                "source_name": "Repeat API",
                "source_type": "API",
                "target_name": "repeatField",
                "relation_type": "REQUEST_FIELD",
                "evidence_quote": "repeat",
                "line_start": 5,
                "line_end": 5,
            },
        ],
    }
    graph = GraphRecords(documents=[document], sections=sections, chunks=chunks)
    result, _trace = extract_graph_with_llm(
        LocalStore(tmp_path / ".specimpact"),
        graph,
        AliasCatalog(),
        FakeLLMClient({"ingest_extraction": extraction}),
    )
    assert len(result.relations) == 1
    assert result.evidence[0].source_location.line_start == 3


def test_llm_relation_target_typing_matches_rule_parser(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\ncalls downstream\nwrites account\n", encoding="utf-8")
    document, sections, chunks = load_document(source, source_key="notes.md")
    client = FakeLLMClient(
        {
            "ingest_extraction": {
                "chunk_id": chunks[0].chunk_id,
                "artifacts": [],
                "entities": [],
                "relations": [
                    {
                        "source_name": "Payment API",
                        "source_type": "API",
                        "target_name": "Downstream API",
                        "relation_type": "CALLS",
                        "evidence_quote": "calls downstream",
                        "line_start": 1,
                        "line_end": 1,
                    },
                    {
                        "source_name": "Payment API",
                        "source_type": "API",
                        "target_name": "ACCOUNT_TABLE",
                        "relation_type": "WRITES",
                        "evidence_quote": "writes account",
                        "line_start": 1,
                        "line_end": 1,
                    },
                ],
            }
        }
    )
    result, _trace = extract_graph_with_llm(
        LocalStore(tmp_path / ".specimpact"),
        GraphRecords(documents=[document], sections=sections, chunks=chunks),
        AliasCatalog(),
        client,
    )
    assert {item.artifact_type for item in result.artifacts} >= {"API", "Document", "Table"}
    assert result.entities == []


def test_llm_unknown_relation_type_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Notes\n\nunknown relation\n", encoding="utf-8")
    document, sections, chunks = load_document(source, source_key="notes.md")
    client = FakeLLMClient(
        {
            "ingest_extraction": {
                "chunk_id": chunks[0].chunk_id,
                "artifacts": [],
                "entities": [],
                "relations": [
                    {
                        "source_name": "Payment API",
                        "source_type": "API",
                        "target_name": "field",
                        "relation_type": "UNKNOWN",
                        "evidence_quote": "unknown relation",
                        "line_start": 1,
                        "line_end": 1,
                    }
                ],
            }
        }
    )
    with pytest.raises(ValueError):
        extract_graph_with_llm(
            LocalStore(tmp_path / ".specimpact"),
            GraphRecords(documents=[document], sections=sections, chunks=chunks),
            AliasCatalog(),
            client,
        )


def test_direct_openai_client_requires_consent_even_when_config_is_disabled(
    tmp_path: Path,
) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text("# API: Payment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="External transmission was not approved"):
        ingest_documents(
            LocalStore(tmp_path / ".specimpact"),
            docs,
            llm_client=OpenAILLMClient("test-model"),
        )


def test_llm_trace_does_not_store_quote_reason_or_raw_result(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "notes.md"
    source.write_text("# Notes\n\nconfidential quote\n", encoding="utf-8")
    chunk_id = load_document(source, source_key="notes.md")[2][0].chunk_id
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(
        store,
        docs,
        llm_client=FakeLLMClient(
            {
                "ingest_extraction": {
                    "chunk_id": chunk_id,
                    "artifacts": [],
                    "entities": [],
                    "relations": [
                        {
                            "source_name": "Payment API",
                            "source_type": "API",
                            "target_name": "secretField",
                            "relation_type": "REQUEST_FIELD",
                            "evidence_quote": "confidential quote",
                            "line_start": 1,
                            "line_end": 1,
                        }
                    ],
                }
            }
        ),
    )
    trace = (store.root / "trace.jsonl").read_text(encoding="utf-8")
    assert "confidential quote" not in trace
    assert '"result":' not in trace
    assert '"result_summary":' in trace


def test_stale_embeddings_are_filtered_without_rebuild(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    config = load_config(store)
    config["embeddings"] = {"enabled": True, "provider": "fake", "model": "fake-model"}
    save_config(store, config)
    store.write("chunks", [_chunk("chunk.current", "current")])
    _write_records(
        store,
        [
            EmbeddingRecord(
                chunk_id="chunk.deleted",
                content_hash="deleted",
                provider="fake",
                model="fake-model",
                vector=[1.0, 0.0],
            ),
            EmbeddingRecord(
                chunk_id="chunk.current",
                content_hash="current",
                provider="fake",
                model="fake-model",
                vector=[0.0, 1.0],
            ),
        ],
    )
    client = FakeEmbeddingClient({"query": [1.0, 0.0]})
    assert semantic_search(store, "query", top_k=2, client=client) == [("chunk.current", 0.0)]


def test_ingest_prunes_embeddings_for_deleted_documents(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "first.md").write_text("# API: First\n", encoding="utf-8")
    (docs / "second.md").write_text("# API: Second\n", encoding="utf-8")
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs)
    assert rebuild_embeddings(store, provider="fake", client=FakeEmbeddingClient()) == 2
    deleted_chunk = next(
        item.chunk_id for item in store.read("chunks", Chunk) if "second" in item.chunk_id
    )
    (docs / "second.md").unlink()
    ingest_documents(store, docs)
    assert deleted_chunk not in {item.chunk_id for item in _read_records(store)}


def test_ollama_url_userinfo_is_rejected_and_redacted_for_legacy_config(
    tmp_path: Path,
) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    with pytest.raises(ValueError, match="must not contain userinfo"):
        configure_llm(store, "ollama", "test-model", "http://user:secret@localhost:11434")
    store.init()
    config = load_config(store)
    config["llm"] = {
        "enabled": True,
        "provider": "ollama",
        "model": "test-model",
        "base_url": "http://user:secret@localhost:11434",
    }
    save_config(store, config)
    status = llm_status(store)
    assert status["base_url"] == "http://[REDACTED]@localhost:11434"
    assert "secret" not in json.dumps(status)


def test_rerank_guardrails_cap_promotions_and_keep_no_impact() -> None:
    direct = _impact("must_review", "direct_match")
    direct.llm_judgement = "no_impact"
    _apply_rerank_guardrails(direct)
    assert direct.review_priority == "must_review"

    semantic = _impact("may_review", "inferred_relation")
    semantic.llm_judgement = "impact"
    semantic.selected_evidence_ids = ["ev.1"]
    _apply_rerank_guardrails(semantic)
    assert semantic.review_priority == "should_review"

    possible = _impact("should_review", "inferred_relation")
    possible.llm_judgement = "no_impact"
    _apply_rerank_guardrails(possible)
    assert possible.review_priority == "may_review"


def test_analyze_batches_llm_rerank_candidates(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "payment.md").write_text(
        "\n".join(
            [
                "# API: Payment API",
                "",
                "## Request fields",
                "- amount",
                "",
                "# Screen: Payment Entry",
                "",
                "## Displays",
                "- amount",
            ]
        ),
        encoding="utf-8",
    )
    change = tmp_path / "change.md"
    change.write_text("# amount change\n\namount limit changed.\n", encoding="utf-8")
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs)
    amount = next(item for item in store.read("entities", Entity) if item.display_name == "amount")

    class CountingClient(FakeLLMClient):
        def __init__(self) -> None:
            super().__init__(
                {
                    "change_extraction": {
                        "changed_entities": [
                            {
                                "entity_id": amount.entity_id,
                                "name": amount.display_name,
                                "reason": "mentioned",
                            }
                        ]
                    }
                }
            )
            self.purposes: list[str] = []

        def structured(self, purpose, payload, schema):
            self.purposes.append(purpose)
            return super().structured(purpose, payload, schema)

    client = CountingClient()
    analyze_change(store, change, llm_client=client)

    assert client.purposes == ["change_extraction", "rerank_batch"]
    rows = [
        json.loads(line)
        for line in (latest_run_dir(store) / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row.get("purpose") for row in rows if row.get("event") == "llm"] == [
        "change_extraction",
        "rerank_batch",
    ]
    batch_summary = next(
        row["result_summary"] for row in rows if row.get("purpose") == "rerank_batch"
    )
    assert batch_summary["result_count"] >= 2
    assert "llm_reason" not in json.dumps(batch_summary)


def test_openai_cli_requires_confirmation_before_ingest(tmp_path: Path, monkeypatch) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text("# API: Payment\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    configured = runner.invoke(
        app,
        ["llm", "configure", "--provider", "openai", "--model", "test-model"],
    )
    assert configured.exit_code == 0
    rejected = runner.invoke(app, ["ingest", str(docs)], input="n\n")
    assert rejected.exit_code == 2
    assert "External transmission was not approved" in rejected.output


def test_backend_update_preserves_graphrag_config(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    configure_llm(store, "fake", "fake-model")
    from specimpact.integrations import configure_backend

    configure_backend(store, "neo4j", "bolt://localhost:7687")
    config = load_config(store)
    assert config["llm"]["model"] == "fake-model"
    assert config["backend"] == "neo4j"


def test_openai_responses_api_retries_invalid_json_and_uses_strict_schema(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    calls = []
    responses = iter(
        [
            b"{",
            b"{",
            json.dumps({"output_text": '{"changed_entities": []}'}).encode(),
        ]
    )

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _Response(next(responses))

    monkeypatch.setattr("specimpact.graphrag.urlopen", fake_urlopen)
    result = OpenAILLMClient("test-model").structured(
        "change_extraction",
        {"change_request": "test"},
        ChangeExtraction,
    )
    assert result.changed_entities == []
    assert len(calls) == 3
    payload = json.loads(calls[-1].data)
    schema = payload["text"]["format"]["schema"]
    assert schema["required"] == ["changed_entities"]
    assert schema["additionalProperties"] is False


def test_ollama_chat_uses_structured_output_schema(monkeypatch) -> None:
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _Response(b'{"message":{"content":"{\\"changed_entities\\":[]}"}}')

    monkeypatch.setattr("specimpact.graphrag.urlopen", fake_urlopen)
    result = OllamaLLMClient("test-model", "http://localhost:11434").structured(
        "change_extraction",
        {"change_request": "test"},
        ChangeExtraction,
    )
    assert result.changed_entities == []
    assert calls[0].full_url == "http://localhost:11434/api/chat"
    payload = json.loads(calls[0].data)
    assert payload["format"]["additionalProperties"] is False


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=f"doc.{chunk_id}",
        section_id=f"sec.{chunk_id}",
        text=text,
        line_start=1,
        line_end=1,
    )


def _impact(priority: str, assessment: str) -> Impact:
    return Impact(
        artifact_id="api.payment",
        display_name="Payment",
        artifact_type="API",
        review_priority=priority,
        evidence_strength="strong",
        match_type="semantic",
        relation_distance=1,
        rule_assessment=assessment,
        reason="test",
        relation_paths=["change -> api.payment"],
        evidence_ids=[],
        needs_review=True,
    )


def _snapshot(store: LocalStore) -> dict[str, bytes]:
    return {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    }


class _Response:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self) -> bytes:
        return self.body


class _RecordingEmbeddingClient:
    def __init__(
        self,
        *,
        provider: str,
        model: str,
        vectors: dict[str, list[float]] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.vectors = vectors or {}
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls.append(texts)
        return [self.vectors.get(text, [1.0, 0.0]) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls.append(text)
        return self.vectors.get(text, [1.0, 0.0])
