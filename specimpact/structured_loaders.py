from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode

from specimpact.extraction import (
    AliasCatalog,
    GraphRecords,
    artifact_for,
    entity_for,
    make_document,
    relation_with_evidence,
)
from specimpact.store import LocalStore


def ingest_openapi(store: LocalStore, path: Path) -> list[dict[str, Any]]:
    store.init()
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    data = _read_structured(path)
    _validate_openapi(data, path)
    document, section, chunk = make_document(path, "openapi", source_key=path.name)
    graph = GraphRecords(documents=[document], sections=[section], chunks=[chunk])
    field_lines = _openapi_field_lines(chunk.text)
    schemas = sorted(data.get("components", {}).get("schemas", {}))
    records = []
    for endpoint, methods in data.get("paths", {}).items():
        for method, operation in methods.items():
            normalized_method = str(method).lower()
            if normalized_method not in {"get", "post", "put", "patch", "delete"}:
                continue
            request_fields = _schema_fields(
                operation.get("requestBody", {}).get("content", {}).get("application/json", {})
            )
            response_fields = sorted(
                {
                    field
                    for response in operation.get("responses", {}).values()
                    for field in _schema_fields(
                        response.get("content", {}).get("application/json", {})
                    )
                }
            )
            operation_id = operation.get("operationId", f"{normalized_method}_{endpoint}")
            artifact = artifact_for(operation_id, "API", document.document_id, aliases)
            graph.artifacts.append(artifact)
            records.append(
                {
                    "artifact_id": artifact.artifact_id,
                    "artifact_type": "API",
                    "display_name": operation_id,
                    "method": normalized_method.upper(),
                    "endpoint": endpoint,
                    "request_fields": request_fields,
                    "response_fields": response_fields,
                    "schemas": schemas,
                    "source": path.as_posix(),
                }
            )
            for relation_type, fields in (
                ("REQUEST_FIELD", request_fields),
                ("RESPONSE_FIELD", response_fields),
            ):
                for field in fields:
                    _add_field_relation(
                        graph,
                        artifact.artifact_id,
                        field,
                        relation_type,
                        document,
                        section.section_id,
                        chunk.chunk_id,
                        aliases,
                        field_lines.get((endpoint, normalized_method, relation_type, field), 1),
                    )
    store.merge_graph(**graph.__dict__)
    return records


def ingest_ddl(store: LocalStore, path: Path) -> list[dict[str, Any]]:
    store.init()
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    document, section, chunk = make_document(path, "ddl", source_key=path.name)
    graph = GraphRecords(documents=[document], sections=[section], chunks=[chunk])
    records = []
    for match in re.finditer(r"CREATE\s+TABLE\s+([\w.]+)\s*\((.*?)\);", chunk.text, re.I | re.S):
        table_name, body = match.groups()
        table = artifact_for(table_name, "Table", document.document_id, aliases)
        graph.artifacts.append(table)
        columns = []
        constraints = []
        for raw_match in re.finditer(r"[^,]+", body):
            line = raw_match.group().strip()
            if not line:
                continue
            if re.match(r"(PRIMARY|FOREIGN|UNIQUE|CONSTRAINT|CHECK)\b", line, re.I):
                constraints.append(line)
                continue
            parts = line.split()
            column_name = parts[0]
            columns.append({"name": column_name, "type": parts[1] if len(parts) > 1 else "unknown"})
            if any(token in line.upper() for token in ("PRIMARY KEY", "NOT NULL", "UNIQUE")):
                constraints.append(line)
            full_name = f"{table_name}.{column_name}"
            column = artifact_for(full_name, "Column", document.document_id, aliases)
            entity = entity_for(full_name, document.document_id, aliases)
            graph.artifacts.append(column)
            graph.entities.append(entity)
            relation, evidence = relation_with_evidence(
                source_id=column.artifact_id,
                target_id=entity.entity_id,
                relation_type="DEFINES",
                document=document,
                section_id=section.section_id,
                chunk_id=chunk.chunk_id,
                line_number=_offset_line_number(
                    chunk.text,
                    match.start(2)
                    + raw_match.start()
                    + len(raw_match.group())
                    - len(raw_match.group().lstrip()),
                ),
                quote=line,
                evidence_type="db_column_definition",
            )
            graph.relations.append(relation)
            graph.evidence.append(evidence)
        records.append(
            {
                "artifact_id": table.artifact_id,
                "artifact_type": "Table",
                "display_name": table_name,
                "columns": columns,
                "constraints": constraints,
                "source": path.as_posix(),
            }
        )
    store.merge_graph(**graph.__dict__)
    return records


def _add_field_relation(
    graph: GraphRecords,
    source_id: str,
    field: str,
    relation_type: str,
    document,
    section_id: str,
    chunk_id: str,
    aliases: AliasCatalog,
    line_number: int,
) -> None:
    entity = entity_for(field, document.document_id, aliases)
    graph.entities.append(entity)
    relation, evidence = relation_with_evidence(
        source_id=source_id,
        target_id=entity.entity_id,
        relation_type=relation_type,
        document=document,
        section_id=section_id,
        chunk_id=chunk_id,
        line_number=line_number,
        quote=field,
        evidence_type="api_request_definition"
        if relation_type == "REQUEST_FIELD"
        else "api_response_definition",
    )
    graph.relations.append(relation)
    graph.evidence.append(evidence)


def _schema_fields(media: dict[str, Any]) -> list[str]:
    return sorted(media.get("schema", {}).get("properties", {}))


def _validate_openapi(data: dict[str, Any], path: Path) -> None:
    paths = _optional_mapping(data, "paths", "paths", path)
    components = _optional_mapping(data, "components", "components", path)
    schemas = _optional_mapping(components, "schemas", "components.schemas", path)
    _validate_string_keys(schemas, "components.schemas", path)
    for endpoint, path_item in paths.items():
        if not isinstance(endpoint, str):
            raise _invalid_openapi(path, "paths keys must be strings")
        if not isinstance(path_item, dict):
            raise _invalid_openapi(path, f"paths.{endpoint} must be a mapping")
        for method, operation in path_item.items():
            if str(method).lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(operation, dict):
                raise _invalid_openapi(path, f"paths.{endpoint}.{method} must be a mapping")
            operation_id = operation.get("operationId")
            if operation_id is not None and not isinstance(operation_id, str):
                raise _invalid_openapi(
                    path,
                    f"paths.{endpoint}.{method}.operationId must be a string",
                )
            request_body = _optional_mapping(
                operation,
                "requestBody",
                f"paths.{endpoint}.{method}.requestBody",
                path,
            )
            _validate_content(request_body, f"paths.{endpoint}.{method}.requestBody", path)
            responses = _optional_mapping(
                operation,
                "responses",
                f"paths.{endpoint}.{method}.responses",
                path,
            )
            for status, response in responses.items():
                if not isinstance(response, dict):
                    raise _invalid_openapi(
                        path,
                        f"paths.{endpoint}.{method}.responses.{status} must be a mapping",
                    )
                _validate_content(
                    response,
                    f"paths.{endpoint}.{method}.responses.{status}",
                    path,
                )


def _validate_content(container: dict[str, Any], context: str, path: Path) -> None:
    content = _optional_mapping(container, "content", f"{context}.content", path)
    media = _optional_mapping(
        content,
        "application/json",
        f"{context}.content.application/json",
        path,
    )
    schema = _optional_mapping(media, "schema", f"{context}.content.application/json.schema", path)
    properties = _optional_mapping(
        schema,
        "properties",
        f"{context}.content.application/json.schema.properties",
        path,
    )
    _validate_string_keys(
        properties,
        f"{context}.content.application/json.schema.properties",
        path,
    )


def _optional_mapping(
    container: dict[str, Any],
    key: str,
    context: str,
    path: Path,
) -> dict[str, Any]:
    if key not in container:
        return {}
    value = container[key]
    if not isinstance(value, dict):
        raise _invalid_openapi(path, f"{context} must be a mapping")
    return value


def _validate_string_keys(container: dict[Any, Any], context: str, path: Path) -> None:
    if not all(isinstance(key, str) for key in container):
        raise _invalid_openapi(path, f"{context} keys must be strings")


def _invalid_openapi(path: Path, reason: str) -> ValueError:
    return ValueError(f"Invalid OpenAPI source: {path}: {reason}")


def _read_structured(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"Structured source does not exist: {path}")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise ValueError(f"Invalid structured source: {path}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Structured source must contain a mapping: {path}")
    return data


def _openapi_field_lines(text: str) -> dict[tuple[str, str, str, str], int]:
    root = yaml.compose(text)
    result: dict[tuple[str, str, str, str], int] = {}
    for endpoint, endpoint_node in _mapping_items(_mapping_value(root, "paths")):
        for method, operation_node in _mapping_items(endpoint_node):
            normalized_method = str(method).lower()
            if normalized_method not in {"get", "post", "put", "patch", "delete"}:
                continue
            request_media = _mapping_value(
                _mapping_value(
                    _mapping_value(operation_node, "requestBody"),
                    "content",
                ),
                "application/json",
            )
            for field, line_number in _property_lines(request_media).items():
                result[(endpoint, normalized_method, "REQUEST_FIELD", field)] = line_number
            for _, response_node in _mapping_items(_mapping_value(operation_node, "responses")):
                response_media = _mapping_value(
                    _mapping_value(response_node, "content"),
                    "application/json",
                )
                for field, line_number in _property_lines(response_media).items():
                    result.setdefault(
                        (endpoint, normalized_method, "RESPONSE_FIELD", field),
                        line_number,
                    )
    return result


def _property_lines(media_node: Node | None) -> dict[str, int]:
    properties = _mapping_value(_mapping_value(media_node, "schema"), "properties")
    return {
        key: key_node.start_mark.line + 1
        for key, _, key_node in _mapping_entries(properties)
    }


def _mapping_value(node: Node | None, name: str) -> Node | None:
    return next(
        (value_node for key, value_node, _ in _mapping_entries(node) if key == name),
        None,
    )


def _mapping_items(node: Node | None) -> list[tuple[str, Node]]:
    return [(key, value_node) for key, value_node, _ in _mapping_entries(node)]


def _mapping_entries(node: Node | None) -> list[tuple[str, Node, ScalarNode]]:
    if not isinstance(node, MappingNode):
        return []
    return [
        (key_node.value, value_node, key_node)
        for key_node, value_node in node.value
        if isinstance(key_node, ScalarNode)
    ]


def _offset_line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
