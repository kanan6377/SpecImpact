from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Callable, Protocol
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field

from specimpact.config import load_config, save_config
from specimpact.graphrag import append_trace, transmission_message
from specimpact.models import Chunk, utc_now
from specimpact.store import LocalStore

DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-small"


class EmbeddingRecord(BaseModel):
    chunk_id: str
    content_hash: str
    provider: str
    model: str
    vector: list[float]
    created_at: str = Field(default_factory=utc_now)


class EmbeddingClient(Protocol):
    provider: str
    model: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, text: str) -> list[float]:
        ...


class LocalEmbeddingClient:
    provider = "local"

    def __init__(self, model: str = DEFAULT_LOCAL_MODEL) -> None:
        self.model = model
        self._encoder = None

    def _load(self):
        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise ValueError(
                    'Local embeddings require pip install -e ".[graphrag-local]"'
                ) from error
            self._encoder = SentenceTransformer(self.model)
        return self._encoder

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._load().encode([f"passage: {text}" for text in texts]).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._load().encode([f"query: {text}"])[0].tolist()


class OpenAIEmbeddingClient:
    provider = "openai"

    def __init__(self, model: str, timeout: float = 30.0) -> None:
        self.model = model
        self.timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        request = Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return [
                item["embedding"]
                for item in sorted(payload["data"], key=lambda item: item["index"])
            ]
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError("OpenAI embedding request failed") from error


class FakeEmbeddingClient:
    provider = "fake"

    def __init__(
        self,
        vectors: dict[str, list[float]] | None = None,
        model: str = "fake-model",
    ) -> None:
        self.model = model
        self.vectors = vectors or {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        return self.vectors.get(text, [float(len(text)), 1.0])


def rebuild_embeddings(
    store: LocalStore,
    *,
    provider: str | None = None,
    model: str | None = None,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
    client: EmbeddingClient | None = None,
) -> int:
    store.init()
    config = load_config(store)
    current = config["embeddings"]
    provider = provider or current.get("provider") or "local"
    if provider not in {"local", "openai", "fake"}:
        raise ValueError("embedding provider must be local or openai")
    configured_model = current.get("model") if current.get("provider") == provider else None
    model = (
        model
        or configured_model
        or (DEFAULT_LOCAL_MODEL if provider == "local" else None)
        or ("fake-model" if provider == "fake" else None)
    )
    if not model:
        raise ValueError("embedding model is required")
    chunks = store.read("chunks", Chunk)
    previous = {item.chunk_id: item for item in _read_records(store)}
    unchanged: list[EmbeddingRecord] = []
    pending: list[Chunk] = []
    for chunk in chunks:
        content_hash = _content_hash(chunk.text)
        record = previous.get(chunk.chunk_id)
        if record and (record.content_hash, record.provider, record.model) == (
            content_hash,
            provider,
            model,
        ):
            unchanged.append(record)
        else:
            pending.append(chunk)
    embedding_client = client or _client(provider, model)
    _validate_client(embedding_client, provider, model)
    _ensure_embedding_consent(
        embedding_client,
        purpose="embeddings_rebuild",
        chunk_count=len(pending),
        yes=yes,
        confirm=confirm,
    )
    vectors = embedding_client.embed_documents([item.text for item in pending]) if pending else []
    created = [
        EmbeddingRecord(
            chunk_id=chunk.chunk_id,
            content_hash=_content_hash(chunk.text),
            provider=provider,
            model=model,
            vector=vector,
        )
        for chunk, vector in zip(pending, vectors, strict=True)
    ]
    records = sorted([*unchanged, *created], key=lambda item: item.chunk_id)
    _write_records(store, records)
    append_trace(
        store,
        [
            {
                "event": "embedding",
                "provider": item.provider,
                "model": item.model,
                "purpose": "embeddings_rebuild",
                "chunk_id": item.chunk_id,
                "prompt_hash": item.content_hash,
                "response_hash": _vector_hash(item.vector),
                "created_at": item.created_at,
            }
            for item in created
        ],
    )
    config["embeddings"] = {"enabled": True, "provider": provider, "model": model}
    save_config(store, config)
    return len(created)


def semantic_search(
    store: LocalStore,
    query: str,
    *,
    top_k: int,
    client: EmbeddingClient | None = None,
    yes: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> list[tuple[str, float]]:
    config = load_config(store)["embeddings"]
    if not config.get("enabled"):
        return []
    records = _read_records(store)
    if not records:
        return []
    chunk_ids = {item.chunk_id for item in store.read("chunks", Chunk)}
    records = [item for item in records if item.chunk_id in chunk_ids]
    if not records:
        return []
    embedding_client = client or _client(config["provider"], config["model"])
    _validate_client(embedding_client, config["provider"], config["model"])
    _ensure_embedding_consent(
        embedding_client,
        purpose="semantic_query",
        chunk_count=1,
        yes=yes,
        confirm=confirm,
    )
    query_vector = embedding_client.embed_query(query)
    ranked = sorted(
        ((record.chunk_id, _cosine(query_vector, record.vector)) for record in records),
        key=lambda item: item[1],
        reverse=True,
    )
    return ranked[:top_k]


def _client(provider: str, model: str) -> EmbeddingClient:
    if provider == "local":
        return LocalEmbeddingClient(model)
    if provider == "openai":
        return OpenAIEmbeddingClient(model)
    if provider == "fake":
        return FakeEmbeddingClient(model=model)
    raise ValueError(f"Unknown embedding provider: {provider}")


def _validate_client(client: EmbeddingClient, provider: str, model: str) -> None:
    if client.provider != provider or client.model != model:
        raise ValueError(
            "embedding client provider and model must match the configured embedding provider"
        )


def _ensure_embedding_consent(
    client: EmbeddingClient,
    *,
    purpose: str,
    chunk_count: int,
    yes: bool,
    confirm: Callable[[str], bool] | None,
) -> None:
    if client.provider != "openai" or not chunk_count:
        return
    message = transmission_message(client.provider, client.model, purpose, chunk_count)
    if yes:
        return
    if confirm and confirm(message):
        return
    raise ValueError("External transmission was not approved; pass --yes to approve")


def _read_records(store: LocalStore) -> list[EmbeddingRecord]:
    path = store.root / "embeddings.jsonl"
    if not path.exists():
        return []
    return [
        EmbeddingRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_records(store: LocalStore, records: list[EmbeddingRecord]) -> None:
    store.write_text(
        store.root / "embeddings.jsonl",
        "".join(json.dumps(item.model_dump(), ensure_ascii=False) + "\n" for item in records),
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _vector_hash(vector: list[float]) -> str:
    return hashlib.sha256(json.dumps(vector, separators=(",", ":")).encode("utf-8")).hexdigest()


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(
        sum(item * item for item in right)
    )
    return (
        sum(a * b for a, b in zip(left, right, strict=True)) / denominator
        if denominator
        else 0.0
    )
