from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Literal, Protocol
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from specimpact.config import load_config
from specimpact.extraction import (
    AliasCatalog,
    GraphRecords,
    artifact_for,
    normalize_relation_type,
    relation_with_evidence,
    target_for_relation,
)
from specimpact.models import Chunk, Document, Entity, utc_now
from specimpact.store import LocalStore

ConsentCallback = Callable[[str], bool]
RelationType = Literal[
    "REQUEST_FIELD",
    "RESPONSE_FIELD",
    "DEFINES",
    "READS",
    "WRITES",
    "DISPLAYS",
    "VALIDATES",
    "SENDS",
    "RECEIVES",
    "CALLS",
    "COVERS",
    "ASSERTS",
]


class LLMArtifactCandidate(BaseModel):
    display_name: str
    artifact_type: str


class LLMEntityCandidate(BaseModel):
    display_name: str


class LLMRelationCandidate(BaseModel):
    source_name: str
    source_type: str
    target_name: str
    relation_type: RelationType
    evidence_quote: str
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)


class ChunkExtraction(BaseModel):
    chunk_id: str
    artifacts: list[LLMArtifactCandidate] = Field(default_factory=list)
    entities: list[LLMEntityCandidate] = Field(default_factory=list)
    relations: list[LLMRelationCandidate] = Field(default_factory=list)


class ChangeEntityCandidate(BaseModel):
    entity_id: str | None = None
    name: str
    reason: str


class ChangeExtraction(BaseModel):
    changed_entities: list[ChangeEntityCandidate] = Field(default_factory=list)


class RerankResult(BaseModel):
    llm_judgement: Literal["impact", "possible", "unknown", "no_impact"]
    llm_reason: str
    selected_evidence_ids: list[str] = Field(default_factory=list)


class RerankBatchItem(BaseModel):
    artifact_id: str
    llm_judgement: Literal["impact", "possible", "unknown", "no_impact"]
    llm_reason: str
    selected_evidence_ids: list[str] = Field(default_factory=list)


class RerankBatchResult(BaseModel):
    results: list[RerankBatchItem] = Field(default_factory=list)


class LLMClient(Protocol):
    provider: str
    model: str

    def structured(self, purpose: str, payload: dict[str, Any], schema: type[BaseModel]) -> Any:
        ...


class HTTPJSONClient:
    def __init__(self, *, timeout: float = 30.0, retries: int = 2) -> None:
        self.timeout = timeout
        self.retries = retries

    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **(headers or {})},
            method="POST",
        )
        last_error: OSError | ValueError | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ValueError("Provider response must be a JSON object")
                return result
            except (OSError, ValueError) as error:
                last_error = error
                if attempt < self.retries:
                    time.sleep(0.1 * (attempt + 1))
        raise ValueError(
            f"Provider request failed after {self.retries + 1} attempts"
        ) from last_error


class OpenAILLMClient(HTTPJSONClient):
    provider = "openai"

    def __init__(self, model: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.model = model

    def structured(self, purpose: str, payload: dict[str, Any], schema: type[BaseModel]) -> Any:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        response = self._post(
            "https://api.openai.com/v1/responses",
            {
                "model": self.model,
                "input": [
                    {
                        "role": "system",
                        "content": (
                            "Return JSON only. Use only the supplied evidence. "
                            f"SpecImpact purpose: {purpose}."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "strict": True,
                        "schema": _strict_schema(schema),
                    }
                },
            },
            {"Authorization": f"Bearer {api_key}"},
        )
        return _validate_output(schema, _openai_output_text(response))


class OllamaLLMClient(HTTPJSONClient):
    provider = "ollama"

    def __init__(self, model: str, base_url: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.model = model
        self.base_url = validate_ollama_base_url(base_url)

    def structured(self, purpose: str, payload: dict[str, Any], schema: type[BaseModel]) -> Any:
        response = self._post(
            f"{self.base_url}/api/chat",
            {
                "model": self.model,
                "stream": False,
                "format": _strict_schema(schema),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return JSON only. Use only the supplied evidence. "
                            f"SpecImpact purpose: {purpose}."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        content = response.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ValueError("Ollama response did not contain message.content")
        return _validate_output(schema, content)


class CodexCLIClient:
    provider = "codex"

    def __init__(
        self,
        model: str,
        *,
        executable: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        self.model = model
        self.executable = executable or shutil.which("codex.cmd") or shutil.which("codex")
        self.timeout = timeout
        if not self.executable:
            raise ValueError("Codex CLI executable was not found")

    def structured(self, purpose: str, payload: dict[str, Any], schema: type[BaseModel]) -> Any:
        prompt = (
            "Act only as a structured JSON extraction backend. "
            "Do not use tools, inspect files, or execute commands. "
            "Return only JSON matching the provided schema. "
            "Use only the supplied payload as evidence. "
            f"SpecImpact purpose: {purpose}.\n"
            f"Payload:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        with tempfile.TemporaryDirectory(prefix="specimpact-codex-") as directory:
            root = Path(directory)
            schema_path = root / "schema.json"
            output_path = root / "output.json"
            schema_path.write_text(
                json.dumps(_strict_schema(schema), ensure_ascii=False),
                encoding="utf-8",
            )
            command = [
                self.executable,
                "exec",
                "--ephemeral",
                "--skip-git-repo-check",
                "--ignore-user-config",
                "--ignore-rules",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--cd",
                str(root),
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            if self.model != "default":
                command[command.index("--cd"):command.index("--cd")] = ["--model", self.model]
            try:
                completed = subprocess.run(
                    command,
                    input=prompt.encode("utf-8"),
                    capture_output=True,
                    timeout=self.timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise ValueError("Codex CLI provider execution failed") from error
            if completed.returncode != 0 or not output_path.is_file():
                raise ValueError("Codex CLI provider execution failed")
            try:
                content = output_path.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError("Codex CLI provider output could not be read") from error
        return _validate_output(schema, content)


class FakeLLMClient:
    """Deterministic provider used by unit tests and offline integrations."""

    provider = "fake"

    def __init__(
        self,
        responses: dict[str, dict[str, Any] | list[dict[str, Any]]] | None = None,
        model: str = "fake-model",
    ) -> None:
        self.model = model
        self.responses = responses or {}

    def structured(self, purpose: str, payload: dict[str, Any], schema: type[BaseModel]) -> Any:
        value = self.responses.get(purpose)
        if isinstance(value, list):
            value = value.pop(0) if value else None
        if value is None:
            value = _empty_fake_value(schema, payload)
        return schema.model_validate(value)

    def judge(self, _change: str, _candidate: str) -> str:
        return "unknown"


def configure_llm(
    store: LocalStore,
    provider: str,
    model: str,
    base_url: str | None = None,
) -> None:
    if provider not in {"openai", "ollama", "codex", "fake"}:
        raise ValueError("provider must be openai, ollama, codex, or fake")
    if not model.strip():
        raise ValueError("LLM model is required when enabling a provider")
    if provider == "ollama" and not base_url:
        raise ValueError("ollama provider requires --base-url")
    if provider == "ollama":
        base_url = validate_ollama_base_url(base_url)
    config = load_config(store)
    config["llm"] = {
        "enabled": True,
        "provider": provider,
        "model": model,
        "base_url": base_url if provider == "ollama" else None,
    }
    from specimpact.config import save_config

    save_config(store, config)


def disable_llm(store: LocalStore) -> None:
    config = load_config(store)
    config["llm"] = {
        "enabled": False,
        "provider": None,
        "model": None,
        "base_url": None,
    }
    from specimpact.config import save_config

    save_config(store, config)


def llm_status(store: LocalStore) -> dict[str, Any]:
    llm = load_config(store)["llm"]
    return {
        "enabled": bool(llm.get("enabled")),
        "provider": llm.get("provider"),
        "model": llm.get("model"),
        "base_url": redact_url(llm.get("base_url")),
        "external_transmission": is_external_llm(llm),
    }


def client_from_config(store: LocalStore) -> LLMClient | None:
    llm = load_config(store)["llm"]
    if not llm.get("enabled"):
        return None
    provider = llm.get("provider")
    model = llm.get("model")
    if not isinstance(model, str) or not model:
        raise ValueError("LLM model is required when enabling a provider")
    if provider == "openai":
        return OpenAILLMClient(model)
    if provider == "ollama":
        base_url = llm.get("base_url")
        if not isinstance(base_url, str) or not base_url:
            raise ValueError("ollama provider requires base_url")
        return OllamaLLMClient(model, base_url)
    if provider == "codex":
        return CodexCLIClient(model)
    if provider == "fake":
        return FakeLLMClient(model=model)
    raise ValueError(f"Unknown LLM provider: {provider}")


def ensure_llm_consent(
    client: LLMClient,
    *,
    purpose: str,
    chunk_count: int,
    yes: bool,
    confirm: ConsentCallback | None,
) -> None:
    if not is_external_client(client):
        return
    message = transmission_message(client.provider, client.model, purpose, chunk_count)
    if yes:
        return
    if confirm and confirm(message):
        return
    raise ValueError("External transmission was not approved; pass --yes to approve")


def is_external_llm(llm: dict[str, Any]) -> bool:
    if not llm.get("enabled"):
        return False
    if llm.get("provider") == "openai":
        return True
    if llm.get("provider") == "codex":
        return True
    if llm.get("provider") == "ollama":
        return not is_loopback_url(str(llm.get("base_url") or ""))
    return False


def is_external_client(client: LLMClient) -> bool:
    if client.provider == "openai":
        return True
    if client.provider == "codex":
        return True
    if client.provider == "ollama":
        return not is_loopback_url(str(getattr(client, "base_url", "")))
    return False


def is_loopback_url(url: str) -> bool:
    try:
        hostname = urlparse(url).hostname
        return bool(hostname and ipaddress.ip_address(hostname).is_loopback)
    except ValueError:
        return urlparse(url).hostname == "localhost"


def validate_ollama_base_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ollama base_url must be an http or https URL")
    if parsed.username or parsed.password:
        raise ValueError("ollama base_url must not contain userinfo")
    return url.rstrip("/")


def redact_url(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        port = ""
    return parsed._replace(netloc=f"[REDACTED]@{host}{port}").geturl()


def transmission_message(provider: str, model: str, purpose: str, chunk_count: int) -> str:
    return (
        f"External transmission: provider={provider}, model={model}, "
        f"purpose={purpose}, chunks={chunk_count}. Continue?"
    )


def extract_graph_with_llm(
    _store: LocalStore,
    graph: GraphRecords,
    aliases: AliasCatalog,
    client: LLMClient,
) -> tuple[GraphRecords, list[dict[str, Any]]]:
    result = GraphRecords()
    documents = {item.document_id: item for item in graph.documents}
    traces: list[dict[str, Any]] = []
    for chunk in graph.chunks:
        payload = {"chunk_id": chunk.chunk_id, "text": chunk.text}
        extraction = client.structured("ingest_extraction", payload, ChunkExtraction)
        if extraction.chunk_id != chunk.chunk_id:
            raise ValueError(f"LLM extraction returned the wrong chunk ID: {extraction.chunk_id}")
        document = documents[chunk.document_id]
        result.extend(_graph_from_extraction(extraction, chunk, document, aliases))
        traces.append(_trace_row(client, "ingest_extraction", chunk.chunk_id, payload, extraction))
    return result, traces


def extract_changed_entities(
    store: LocalStore,
    body: str,
    client: LLMClient,
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    entities = {item.entity_id: item for item in store.read("entities", Entity)}
    payload = {
        "change_request": body,
        "known_entities": [
            {
                "entity_id": item.entity_id,
                "display_name": item.display_name,
                "aliases": item.aliases,
            }
            for item in entities.values()
        ],
    }
    extraction = client.structured("change_extraction", payload, ChangeExtraction)
    matched: list[str] = []
    suggestions: list[dict[str, str]] = []
    for candidate in extraction.changed_entities:
        if candidate.entity_id in entities:
            matched.append(candidate.entity_id)
            continue
        by_name = next(
            (
                item.entity_id
                for item in entities.values()
                if candidate.name in {item.display_name, item.canonical_name, *item.aliases}
            ),
            None,
        )
        if by_name:
            matched.append(by_name)
        else:
            suggestions.append(candidate.model_dump(exclude_none=True))
    return sorted(set(matched)), suggestions, _trace_row(
        client, "change_extraction", None, payload, extraction
    )


def rerank(
    client: LLMClient,
    payload: dict[str, Any],
) -> tuple[RerankResult, dict[str, Any]]:
    result = client.structured("rerank", payload, RerankResult)
    if result.llm_judgement not in {"impact", "possible", "unknown", "no_impact"}:
        raise ValueError(f"Invalid LLM judgement: {result.llm_judgement}")
    allowed = {
        evidence["evidence_id"]
        for evidence in payload.get("evidence", [])
        if isinstance(evidence, dict) and isinstance(evidence.get("evidence_id"), str)
    }
    result.selected_evidence_ids = [
        evidence_id for evidence_id in result.selected_evidence_ids if evidence_id in allowed
    ]
    return result, _trace_row(client, "rerank", None, payload, result)


def rerank_batch(
    client: LLMClient,
    payload: dict[str, Any],
) -> tuple[dict[str, RerankBatchItem], dict[str, Any]]:
    result = client.structured("rerank_batch", payload, RerankBatchResult)
    candidates = {
        candidate["artifact_id"]: candidate
        for candidate in payload.get("candidates", [])
        if isinstance(candidate, dict) and isinstance(candidate.get("artifact_id"), str)
    }
    evidence_by_artifact = {
        artifact_id: {
            evidence["evidence_id"]
            for evidence in candidate.get("evidence", [])
            if isinstance(evidence, dict) and isinstance(evidence.get("evidence_id"), str)
        }
        for artifact_id, candidate in candidates.items()
    }
    cleaned: dict[str, RerankBatchItem] = {}
    for item in result.results:
        if item.artifact_id not in candidates:
            continue
        if item.llm_judgement not in {"impact", "possible", "unknown", "no_impact"}:
            raise ValueError(f"Invalid LLM judgement: {item.llm_judgement}")
        allowed = evidence_by_artifact[item.artifact_id]
        item.selected_evidence_ids = [
            evidence_id for evidence_id in item.selected_evidence_ids if evidence_id in allowed
        ]
        cleaned[item.artifact_id] = item
    return cleaned, _trace_row(client, "rerank_batch", None, payload, result)


def append_trace(store: LocalStore, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path = store.root / "trace.jsonl"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rendered = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    store.write_text(path, existing + rendered)


def _graph_from_extraction(
    extraction: ChunkExtraction,
    chunk: Chunk,
    document: Document,
    aliases: AliasCatalog,
) -> GraphRecords:
    graph = GraphRecords()
    for candidate in extraction.relations:
        if candidate.source_type not in {
            "API",
            "Screen",
            "Table",
            "Column",
            "ValidationRule",
            "ExternalIF",
            "TestCase",
            "Batch",
            "Document",
        }:
            continue
        quote_location = _quote_location(chunk, candidate.evidence_quote)
        if not quote_location:
            continue
        source = artifact_for(
            candidate.source_name,
            candidate.source_type,
            document.document_id,
            aliases,
        )
        source.extraction_methods = ["llm"]
        graph.artifacts.append(source)
        relation_type = normalize_relation_type(source, candidate.relation_type)
        target = target_for_relation(
            graph,
            candidate.target_name,
            relation_type,
            document,
            aliases,
        )
        target.extraction_methods = ["llm"]
        target_id = getattr(target, "artifact_id", getattr(target, "entity_id", ""))
        line_start, line_end = quote_location
        relation, evidence = relation_with_evidence(
            source_id=source.artifact_id,
            target_id=target_id,
            relation_type=relation_type,
            document=document,
            section_id=chunk.section_id,
            chunk_id=chunk.chunk_id,
            line_number=line_start,
            line_end=line_end,
            quote=candidate.evidence_quote,
            evidence_type="llm_inferred_relation",
            match_type="semantic",
            target_support_type="entity" if isinstance(target, Entity) else "artifact",
        )
        relation.extraction_method = "llm"
        relation.polarity = "inferred"
        relation.status = "unconfirmed"
        graph.relations.append(relation)
        graph.evidence.append(evidence)
    return graph


def _trace_row(
    client: LLMClient,
    purpose: str,
    chunk_id: str | None,
    payload: dict[str, Any],
    result: BaseModel,
) -> dict[str, Any]:
    return {
        "event": "llm",
        "provider": client.provider,
        "model": client.model,
        "purpose": purpose,
        "chunk_id": chunk_id,
        "prompt_hash": _hash(payload),
        "response_hash": _hash(result.model_dump()),
        "result_summary": _result_summary(result),
        "created_at": utc_now(),
    }


def _quote_location(chunk: Chunk, raw_quote: str) -> tuple[int, int] | None:
    quote = raw_quote.strip()
    if not quote:
        return None
    offsets = []
    offset = chunk.text.find(quote)
    while offset >= 0:
        offsets.append(offset)
        offset = chunk.text.find(quote, offset + 1)
    if len(offsets) != 1:
        return None
    line_start = chunk.line_start + chunk.text.count("\n", 0, offsets[0])
    return line_start, line_start + quote.count("\n")


def _result_summary(result: BaseModel) -> dict[str, Any]:
    if isinstance(result, ChunkExtraction):
        return {
            "chunk_id": result.chunk_id,
            "artifact_count": len(result.artifacts),
            "entity_count": len(result.entities),
            "relation_count": len(result.relations),
        }
    if isinstance(result, ChangeExtraction):
        return {
            "changed_entity_ids": sorted(
                candidate.entity_id
                for candidate in result.changed_entities
                if candidate.entity_id
            ),
            "suggestion_count": sum(
                candidate.entity_id is None for candidate in result.changed_entities
            ),
        }
    if isinstance(result, RerankResult):
        return {
            "llm_judgement": result.llm_judgement,
            "selected_evidence_ids": result.selected_evidence_ids,
        }
    if isinstance(result, RerankBatchResult):
        judgement_counts: dict[str, int] = {}
        for item in result.results:
            judgement_counts[item.llm_judgement] = judgement_counts.get(item.llm_judgement, 0) + 1
        return {
            "result_count": len(result.results),
            "judgement_counts": judgement_counts,
            "selected_evidence_count": sum(
                len(item.selected_evidence_ids) for item in result.results
            ),
        }
    return {}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _validate_output(schema: type[BaseModel], content: str) -> BaseModel:
    try:
        return schema.model_validate_json(content)
    except ValidationError as error:
        raise ValueError(f"Provider output did not match {schema.__name__}") from error


def _strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    result = schema.model_json_schema()

    def normalize(value: Any) -> None:
        if isinstance(value, dict):
            value.pop("default", None)
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
                value["additionalProperties"] = False
            for child in value.values():
                normalize(child)
        elif isinstance(value, list):
            for child in value:
                normalize(child)

    normalize(result)
    return result


def _openai_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    for output in response.get("output", []):
        for content in output.get("content", []):
            if isinstance(content.get("text"), str):
                return content["text"]
            if content.get("type") == "refusal":
                raise ValueError("OpenAI provider refused the structured extraction request")
    raise ValueError("OpenAI response did not contain structured output text")


def _empty_fake_value(schema: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    if schema is ChunkExtraction:
        return {"chunk_id": payload["chunk_id"], "artifacts": [], "entities": [], "relations": []}
    if schema is ChangeExtraction:
        return {"changed_entities": []}
    if schema is RerankResult:
        return {
            "llm_judgement": "unknown",
            "llm_reason": "No fake judgement.",
            "selected_evidence_ids": [],
        }
    if schema is RerankBatchResult:
        return {
            "results": [
                {
                    "artifact_id": candidate["artifact_id"],
                    "llm_judgement": "unknown",
                    "llm_reason": "No fake judgement.",
                    "selected_evidence_ids": [],
                }
                for candidate in payload.get("candidates", [])
                if isinstance(candidate, dict) and isinstance(candidate.get("artifact_id"), str)
            ]
        }
    return {}
