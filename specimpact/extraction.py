from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from specimpact.models import (
    Artifact,
    Chunk,
    Document,
    Entity,
    Evidence,
    EvidenceSupport,
    Relation,
    Section,
    SourceLocation,
)

ARTIFACT_TYPES = {
    "api": "API",
    "screen": "Screen",
    "table": "Table",
    "column": "Column",
    "validationrule": "ValidationRule",
    "externalif": "ExternalIF",
    "testcase": "TestCase",
    "batch": "Batch",
    "document": "Document",
}
ALIAS_CANONICAL_TYPES = {*ARTIFACT_TYPES.values(), "BusinessField"}
PREFIXES = {
    "API": "api",
    "Screen": "screen",
    "Table": "table",
    "Column": "column",
    "ValidationRule": "validation",
    "ExternalIF": "external_if",
    "TestCase": "test",
    "Batch": "batch",
    "Document": "document",
}
RELATION_HEADINGS = {
    "request fields": "REQUEST_FIELD",
    "response fields": "RESPONSE_FIELD",
    "fields": "DEFINES",
    "reads": "READS",
    "uses": "READS",
    "writes": "WRITES",
    "displays": "DISPLAYS",
    "validates": "VALIDATES",
    "target": "VALIDATES",
    "sends": "SENDS",
    "receives": "RECEIVES",
    "calls": "CALLS",
    "covers": "COVERS",
    "asserts": "ASSERTS",
}
FIELD_RELATIONS = {
    "REQUEST_FIELD",
    "RESPONSE_FIELD",
    "DEFINES",
    "READS",
    "DISPLAYS",
    "VALIDATES",
    "SENDS",
    "RECEIVES",
    "ASSERTS",
}


@dataclass
class GraphRecords:
    documents: list[Document] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    def extend(self, other: GraphRecords) -> None:
        for name in self.__dataclass_fields__:
            getattr(self, name).extend(getattr(other, name))


class AliasCatalog:
    def __init__(self, entries: dict[str, dict[str, object]] | None = None) -> None:
        self.entries = entries or {}

    @classmethod
    def load(cls, path: Path) -> AliasCatalog:
        if not path.exists() or not path.read_text(encoding="utf-8").strip():
            return cls()
        return cls.parse(path.read_text(encoding="utf-8"), path)

    @classmethod
    def parse(cls, text: str, path: Path | str = "aliases.yml") -> AliasCatalog:
        try:
            data = yaml.safe_load(text) or {}
        except yaml.YAMLError as error:
            raise ValueError(f"Invalid aliases YAML: {path}") from error
        if not isinstance(data, dict):
            raise ValueError("aliases.yml must contain a mapping")
        aliases = data.get("aliases", {})
        if not isinstance(aliases, dict):
            raise ValueError("aliases.yml must contain an aliases mapping")
        catalog = cls(aliases)
        catalog.validate()
        return catalog

    def validate(self) -> None:
        seen: dict[str, str] = {}
        for item_id, details in self.entries.items():
            if not isinstance(item_id, str) or not isinstance(details, dict):
                raise ValueError("Each alias entry must be a mapping keyed by a string ID")
            canonical_type = details.get("canonical_type")
            if canonical_type not in ALIAS_CANONICAL_TYPES:
                allowed = ", ".join(sorted(ALIAS_CANONICAL_TYPES))
                raise ValueError(f"canonical_type must be one of: {allowed}")
            aliases = details.get("aliases")
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                raise ValueError("Each alias entry must contain aliases as a list of strings")
            for alias in {item_id, *self.aliases_for(item_id)}:
                if alias in seen and seen[alias] != item_id:
                    raise ValueError(
                        f'Ambiguous alias "{alias}" is assigned to {seen[alias]} and {item_id}'
                    )
                seen[alias] = item_id

    def aliases_for(self, item_id: str) -> list[str]:
        details = self.entries.get(item_id, {})
        aliases = details.get("aliases", []) if isinstance(details, dict) else []
        return [str(alias) for alias in aliases]

    def canonical_id(self, name: str, item_type: str | None = None) -> str | None:
        for item_id, details in self.entries.items():
            if not isinstance(details, dict):
                continue
            canonical_type = str(details.get("canonical_type", ""))
            aliases = {item_id, *self.aliases_for(item_id)}
            if name in aliases and (
                not item_type or not canonical_type or canonical_type == item_type
            ):
                return item_id
        return None

    def canonical_type(self, name: str) -> str | None:
        for item_id, details in self.entries.items():
            if name in {item_id, *self.aliases_for(item_id)} and isinstance(details, dict):
                return str(details.get("canonical_type", "")) or None
        return None


def extract_markdown(
    document: Document,
    sections: list[Section],
    chunks: list[Chunk],
    aliases: AliasCatalog,
) -> GraphRecords:
    path = Path(document.path)
    lines = path.read_text(encoding="utf-8").splitlines()
    graph = GraphRecords(documents=[document], sections=sections, chunks=chunks)
    root = _root_artifact(document, lines, aliases)
    current = root
    relation_type: str | None = None
    has_named_artifacts = False
    if root:
        graph.artifacts.append(root)
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            text = heading.group(1).strip()
            named = _named_artifact(text, aliases, document.document_id)
            if named:
                has_named_artifacts = True
                current = named
                relation_type = "DEFINES" if named.artifact_type == "Table" else None
                graph.artifacts.append(named)
                continue
            relation_type = RELATION_HEADINGS.get(text.lower())
            if not relation_type and root:
                current = root
            continue
        inline = re.match(r"^([A-Za-z ]+):\s*(.+)$", line)
        if inline and inline.group(1).strip().lower() in RELATION_HEADINGS:
            relation_type = RELATION_HEADINGS[inline.group(1).strip().lower()]
            for value in _split_values(inline.group(2)):
                _add_relation(
                    graph,
                    current,
                    relation_type,
                    value,
                    document,
                    chunks,
                    number,
                    raw_line,
                    aliases,
                )
            continue
        if line.endswith(":"):
            relation_type = None
            continue
        if line.startswith("- ") and relation_type:
            if current and current.artifact_type == "Table" and relation_type == "DEFINES":
                _add_table_column(
                    graph, current, line[2:].strip(), document, chunks, number, raw_line, aliases
                )
            else:
                _add_relation(
                    graph,
                    current,
                    relation_type,
                    line[2:].strip(),
                    document,
                    chunks,
                    number,
                    raw_line,
                    aliases,
                )
    if not has_named_artifacts:
        _add_plain_mentions(graph, document, chunks, aliases)
    graph.artifacts = _dedupe(graph.artifacts, "artifact_id")
    graph.entities = _dedupe(graph.entities, "entity_id")
    graph.relations, relation_aliases = _dedupe_relations(graph.relations)
    for item in graph.evidence:
        for support in item.supports:
            if support.type == "relation" and support.id in relation_aliases:
                support.id = relation_aliases[support.id]
    graph.evidence = _dedupe(graph.evidence, "evidence_id")
    return graph


def make_document(
    path: Path,
    document_type: str,
    text: str | None = None,
    source_key: str | None = None,
) -> tuple[Document, Section, Chunk]:
    raw = path.read_bytes()
    if text is None:
        text = raw.decode("utf-8") if path.suffix.lower() != ".xlsx" else path.name
    slug = _slug(path.stem)
    document_id = f"doc.{slug}.{_short_hash(source_key or path.name)}"
    section = Section(
        section_id=f"sec.{slug}.{_short_hash(document_id)}.001",
        document_id=document_id,
        heading=path.name,
        level=1,
        line_start=1,
        line_end=max(1, len(text.splitlines())),
    )
    chunk = Chunk(
        chunk_id=f"chunk.{slug}.{_short_hash(document_id)}.001",
        document_id=document_id,
        section_id=section.section_id,
        text=text,
        line_start=section.line_start,
        line_end=section.line_end,
    )
    document = Document(
        document_id=document_id,
        path=path.as_posix(),
        title=path.name,
        document_type=document_type,
        hash=hashlib.sha256(raw).hexdigest(),
    )
    return document, section, chunk


def artifact_for(name: str, item_type: str, document_id: str, aliases: AliasCatalog) -> Artifact:
    artifact_id = aliases.canonical_id(name, item_type) or f"{PREFIXES[item_type]}.{_slug(name)}"
    return Artifact(
        artifact_id=artifact_id,
        artifact_type=item_type,
        display_name=name,
        aliases=aliases.aliases_for(artifact_id),
        source_document_ids=[document_id],
        extraction_methods=["rule"],
    )


def entity_for(name: str, document_id: str, aliases: AliasCatalog) -> Entity:
    clean = _field_name(name)
    leaf = clean.rsplit(".", 1)[-1]
    entity_id = (
        aliases.canonical_id(clean, "BusinessField")
        or (
            aliases.canonical_id(leaf, "BusinessField")
            if aliases.canonical_id(clean, "Column")
            else None
        )
        or f"entity.{_slug(clean)}"
    )
    return Entity(
        entity_id=entity_id,
        entity_type="BusinessField",
        display_name=clean,
        canonical_name=_slug(clean),
        aliases=aliases.aliases_for(entity_id),
        source_document_ids=[document_id],
        extraction_methods=["rule"],
    )


def relation_with_evidence(
    *,
    source_id: str,
    target_id: str,
    relation_type: str,
    document: Document,
    section_id: str,
    chunk_id: str,
    line_number: int,
    quote: str,
    line_end: int | None = None,
    evidence_type: str = "explicit_field_definition",
    match_type: str = "exact",
    target_support_type: str = "entity",
) -> tuple[Relation, Evidence]:
    key = f"{source_id}|{relation_type}|{target_id}|{document.document_id}|{line_number}"
    suffix = _short_hash(key)
    relation_id = f"rel.{_slug(source_id)}.{relation_type.lower()}.{_slug(target_id)}.{suffix}"
    evidence_id = f"ev.{suffix}"
    relation = Relation(
        relation_id=relation_id,
        relation_type=relation_type,
        source_id=source_id,
        target_id=target_id,
        evidence_ids=[evidence_id],
        match_type=match_type,
        source_document_ids=[document.document_id],
    )
    evidence = Evidence(
        evidence_id=evidence_id,
        document_id=document.document_id,
        section_id=section_id,
        chunk_id=chunk_id,
        quote=quote.strip(),
        evidence_type=evidence_type,
        supports=[
            EvidenceSupport(type=target_support_type, id=target_id),
            EvidenceSupport(type="relation", id=relation_id),
        ],
        source_location=SourceLocation(
            file=document.path,
            line_start=line_number,
            line_end=line_end or line_number,
        ),
    )
    return relation, evidence


def _root_artifact(document: Document, lines: list[str], aliases: AliasCatalog) -> Artifact | None:
    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), "")
    if not title:
        return None
    if title.lower().startswith(tuple(f"{key}:" for key in ARTIFACT_TYPES)):
        return _named_artifact(title, aliases, document.document_id)
    lowered = "\n".join(lines).lower()
    item_type = None
    if "## endpoint" in lowered or title.lower().endswith("api"):
        item_type = "API"
    elif "## displays" in lowered or "## fields" in lowered:
        item_type = "Screen"
    elif title.lower().startswith("batch"):
        item_type = "Batch"
    if item_type:
        return artifact_for(title, item_type, document.document_id, aliases)
    return None


def _named_artifact(text: str, aliases: AliasCatalog, document_id: str) -> Artifact | None:
    match = re.match(
        r"^(API|Screen|Table|Column|ValidationRule|ExternalIF|TestCase|Batch|Document)\s*:\s*(.+)$",
        text,
        re.I,
    )
    if not match:
        return None
    item_type = ARTIFACT_TYPES[match.group(1).lower()]
    return artifact_for(match.group(2).strip(), item_type, document_id, aliases)


def _add_relation(
    graph: GraphRecords,
    source: Artifact | None,
    relation_type: str,
    value: str,
    document: Document,
    chunks: list[Chunk],
    line_number: int,
    quote: str,
    aliases: AliasCatalog,
) -> None:
    if not source or not value:
        return
    relation_type = normalize_relation_type(source, relation_type)
    target = target_for_relation(graph, value, relation_type, document, aliases)
    target_id = getattr(target, "artifact_id", getattr(target, "entity_id", ""))
    chunk = _chunk_for_line(chunks, line_number)
    relation, evidence = relation_with_evidence(
        source_id=source.artifact_id,
        target_id=target_id,
        relation_type=relation_type,
        document=document,
        section_id=chunk.section_id,
        chunk_id=chunk.chunk_id,
        line_number=line_number,
        quote=quote,
        evidence_type=_evidence_type(relation_type),
        target_support_type="entity" if isinstance(target, Entity) else "artifact",
    )
    graph.relations.append(relation)
    graph.evidence.append(evidence)


def normalize_relation_type(source: Artifact, relation_type: str) -> str:
    if source.artifact_type == "Screen" and relation_type == "DEFINES":
        return "DISPLAYS"
    return relation_type


def target_for_relation(
    graph: GraphRecords,
    value: str,
    relation_type: str,
    document: Document,
    aliases: AliasCatalog,
) -> Artifact | Entity:
    if relation_type == "READS" and re.fullmatch(r"[A-Z][A-Z0-9_]*", value):
        target = artifact_for(value, "Table", document.document_id, aliases)
        graph.artifacts.append(target)
        return target
    if relation_type in FIELD_RELATIONS:
        target = entity_for(value, document.document_id, aliases)
        graph.entities.append(target)
        return target
    target_type = aliases.canonical_type(value) or (
        "Table" if relation_type == "WRITES" else "Document"
    )
    if target_type not in PREFIXES:
        target_type = "Document"
    target = artifact_for(value, target_type, document.document_id, aliases)
    graph.artifacts.append(target)
    return target


def _add_plain_mentions(
    graph: GraphRecords,
    document: Document,
    chunks: list[Chunk],
    aliases: AliasCatalog,
) -> None:
    root = next(
        (item for item in graph.artifacts if document.document_id in item.source_document_ids), None
    )
    if not root:
        return
    existing = {(item.source_id, item.target_id) for item in graph.relations}
    for item_id, details in aliases.entries.items():
        if not isinstance(details, dict) or details.get("canonical_type") != "BusinessField":
            continue
        for alias in aliases.aliases_for(item_id):
            chunk = next((item for item in chunks if alias and alias in item.text), None)
            if chunk and (root.artifact_id, item_id) not in existing:
                entity = entity_for(alias, document.document_id, aliases)
                graph.entities.append(entity)
                relation, evidence = relation_with_evidence(
                    source_id=root.artifact_id,
                    target_id=item_id,
                    relation_type="MENTIONS",
                    document=document,
                    section_id=chunk.section_id,
                    chunk_id=chunk.chunk_id,
                    line_number=chunk.line_start,
                    quote=alias,
                    evidence_type="plain_mention",
                    match_type="alias",
                )
                graph.relations.append(relation)
                graph.evidence.append(evidence)
                existing.add((root.artifact_id, item_id))
                break


def _add_table_column(
    graph: GraphRecords,
    table: Artifact,
    value: str,
    document: Document,
    chunks: list[Chunk],
    line_number: int,
    quote: str,
    aliases: AliasCatalog,
) -> None:
    full_name = f"{table.display_name}.{_field_name(value)}"
    column = artifact_for(full_name, "Column", document.document_id, aliases)
    entity = entity_for(full_name, document.document_id, aliases)
    graph.artifacts.append(column)
    graph.entities.append(entity)
    chunk = _chunk_for_line(chunks, line_number)
    relation, evidence = relation_with_evidence(
        source_id=column.artifact_id,
        target_id=entity.entity_id,
        relation_type="DEFINES",
        document=document,
        section_id=chunk.section_id,
        chunk_id=chunk.chunk_id,
        line_number=line_number,
        quote=quote,
        evidence_type="db_column_definition",
    )
    graph.relations.append(relation)
    graph.evidence.append(evidence)


def _split_values(text: str) -> Iterable[str]:
    return (item.strip() for item in re.split(r"[,/]", text) if item.strip())


def _field_name(value: str) -> str:
    return value.split(":", 1)[0].strip().split("。", 1)[0].strip()


def _chunk_for_line(chunks: list[Chunk], line_number: int) -> Chunk:
    return next(item for item in chunks if item.line_start <= line_number <= item.line_end)


def _slug(value: str) -> str:
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return ascii_slug or f"item_{_short_hash(value)}"


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:10]


def _dedupe(items: list[object], key: str) -> list:
    return list({getattr(item, key): item for item in items}.values())


def _dedupe_relations(relations: list[Relation]) -> tuple[list[Relation], dict[str, str]]:
    merged: dict[tuple[str, str, str], Relation] = {}
    aliases: dict[str, str] = {}
    for relation in relations:
        key = (relation.source_id, relation.relation_type, relation.target_id)
        if key not in merged:
            merged[key] = relation
            continue
        current = merged[key]
        aliases[relation.relation_id] = current.relation_id
        current.evidence_ids = sorted({*current.evidence_ids, *relation.evidence_ids})
    return list(merged.values()), aliases


def _evidence_type(relation_type: str) -> str:
    return {
        "REQUEST_FIELD": "api_request_definition",
        "RESPONSE_FIELD": "api_response_definition",
        "DEFINES": "explicit_field_definition",
        "DISPLAYS": "screen_display_definition",
        "VALIDATES": "validation_rule_definition",
        "SENDS": "external_mapping_definition",
        "RECEIVES": "external_mapping_definition",
        "COVERS": "test_coverage_definition",
    }.get(relation_type, "plain_mention")
