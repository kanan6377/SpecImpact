from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from specimpact.models import Artifact, Chunk, Document, Entity, Evidence, Relation, Section
from specimpact.schema_validation import validate_evidence, validate_relation

T = TypeVar("T", bound=BaseModel)

COLLECTIONS = ("documents", "sections", "chunks", "artifacts", "entities", "relations", "evidence")


class LocalStore:
    def __init__(self, root: Path | str = ".specimpact") -> None:
        self.root = Path(root)

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "runs").mkdir(exist_ok=True)
        if not (self.root / "config.yml").exists():
            self.write_text(
                self.root / "config.yml",
                "backend: local\n"
                "llm:\n"
                "  enabled: false\n"
                "  provider: null\n"
                "  model: null\n"
                "  base_url: null\n"
                "embeddings:\n"
                "  enabled: false\n"
                "  provider: local\n"
                "  model: intfloat/multilingual-e5-small\n"
                "retrieval:\n"
                "  semantic_top_k: 20\n"
                "  graph_max_hops: 2\n",
            )
        if not (self.root / "aliases.yml").exists():
            self.write_text(self.root / "aliases.yml", "")
        for collection in COLLECTIONS:
            path = self.root / f"{collection}.jsonl"
            if not path.exists():
                self.write_text(path, "")

    def write(self, collection: str, models: list[BaseModel]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        content = "".join(
            json.dumps(model.model_dump(), ensure_ascii=False) + "\n" for model in models
        )
        self.write_text(self.root / f"{collection}.jsonl", content)

    def read(self, collection: str, model: type[T]) -> list[T]:
        path = self.root / f"{collection}.jsonl"
        if not path.exists():
            return []
        return [
            model.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def write_json(self, path: Path, data: Any) -> None:
        self.write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="") as temp:
                temp.write(content)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def merge_graph(
        self,
        *,
        documents: list[Document],
        sections: list[Section],
        chunks: list[Chunk],
        artifacts: list[Artifact],
        entities: list[Entity],
        relations: list[Relation],
        evidence: list[Evidence],
        prune_document_ids: set[str] | None = None,
    ) -> None:
        self.init()
        from specimpact.source_freshness import finalize_graph_merge, prepare_graph_merge

        freshness = prepare_graph_merge(self, documents, prune_document_ids or set())
        self._validate_document_identities(documents)
        replaced = {item.document_id for item in documents} | (prune_document_ids or set())
        current_documents = [
            item for item in self.read("documents", Document) if item.document_id not in replaced
        ]
        current_sections = [
            item for item in self.read("sections", Section) if item.document_id not in replaced
        ]
        current_chunks = [
            item for item in self.read("chunks", Chunk) if item.document_id not in replaced
        ]
        current_evidence = [
            item for item in self.read("evidence", Evidence) if item.document_id not in replaced
        ]
        kept_artifacts = _without_sources(self.read("artifacts", Artifact), replaced)
        kept_entities = _without_sources(self.read("entities", Entity), replaced)
        existing_relations = self.read("relations", Relation)
        statuses = {item.relation_id: item.status for item in existing_relations}
        kept_relations = _without_sources(existing_relations, replaced)
        for relation in relations:
            if set(relation.source_document_ids) & freshness.stale_document_ids:
                relation.status = "unconfirmed"
            elif relation.relation_id in statuses:
                relation.status = statuses[relation.relation_id]
        for relation in relations:
            validate_relation(relation.model_dump())
        for item in evidence:
            validate_evidence(item.model_dump())
        self.write("documents", _unique(current_documents + documents, "document_id"))
        self.write("sections", _unique(current_sections + sections, "section_id"))
        self.write("chunks", _unique(current_chunks + chunks, "chunk_id"))
        self.write("artifacts", _merge_sourced(kept_artifacts + artifacts, "artifact_id"))
        self.write("entities", _merge_sourced(kept_entities + entities, "entity_id"))
        self.write("relations", _merge_relations(kept_relations + relations))
        self.write("evidence", _unique(current_evidence + evidence, "evidence_id"))
        self._prune_embeddings()
        finalize_graph_merge(self, freshness)

    def _validate_document_identities(self, documents: list[Document]) -> None:
        known: dict[str, Document] = {
            item.document_id: item for item in self.read("documents", Document)
        }
        for document in documents:
            current = known.get(document.document_id)
            if current and _resolved_path(current.path) != _resolved_path(document.path):
                raise ValueError(
                    f"Document ID collision: {document.document_id} maps to both "
                    f"{current.path} and {document.path}"
                )
            known[document.document_id] = document

    def prepare_source_manifest(
        self,
        root_id: str,
        document_ids: set[str],
    ) -> tuple[set[str], dict[str, list[str]]]:
        path = self.root / "source_manifests.json"
        manifests = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        previous = set(manifests.get(root_id, []))
        manifests[root_id] = sorted(document_ids)
        return previous - document_ids, manifests

    def write_source_manifests(self, manifests: dict[str, list[str]]) -> None:
        path = self.root / "source_manifests.json"
        self.write_json(path, manifests)

    def _prune_embeddings(self) -> None:
        path = self.root / "embeddings.jsonl"
        if not path.exists():
            return
        chunk_ids = {item.chunk_id for item in self.read("chunks", Chunk)}
        rows = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("chunk_id") in chunk_ids
        ]
        self.write_text(path, "".join(f"{line}\n" for line in rows))


def _without_sources(models: list[T], replaced: set[str]) -> list[T]:
    result = []
    for model in models:
        sources = [item for item in model.source_document_ids if item not in replaced]
        if sources:
            model.source_document_ids = sources
            result.append(model)
    return result


def _unique(models: list[T], key: str) -> list[T]:
    return list({getattr(model, key): model for model in models}.values())


def _merge_sourced(models: list[T], key: str) -> list[T]:
    merged: dict[str, T] = {}
    for model in models:
        item_id = getattr(model, key)
        if item_id not in merged:
            merged[item_id] = model
            continue
        current = merged[item_id]
        current.source_document_ids = sorted(
            {*current.source_document_ids, *model.source_document_ids}
        )
        if hasattr(current, "aliases"):
            current.aliases = sorted({*current.aliases, *model.aliases})
        if hasattr(current, "extraction_methods"):
            current.extraction_methods = sorted(
                {*current.extraction_methods, *model.extraction_methods}
            )
    return list(merged.values())


def _merge_relations(relations: list[Relation]) -> list[Relation]:
    merged: dict[str, Relation] = {}
    for relation in relations:
        if relation.relation_id not in merged:
            merged[relation.relation_id] = relation
            continue
        current = merged[relation.relation_id]
        current.evidence_ids = sorted({*current.evidence_ids, *relation.evidence_ids})
        current.source_document_ids = sorted(
            {*current.source_document_ids, *relation.source_document_ids}
        )
    return list(merged.values())


def _resolved_path(path: str) -> Path:
    return Path(path).resolve()
