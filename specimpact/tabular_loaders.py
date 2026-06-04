from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from specimpact.extraction import (
    AliasCatalog,
    GraphRecords,
    artifact_for,
    entity_for,
    make_document,
    relation_with_evidence,
)
from specimpact.store import LocalStore


def ingest_csv(store: LocalStore, path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"CSV source does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV header row is required")
        rows = list(reader)
    return _ingest_tables(store, path, [(path.stem, reader.fieldnames, rows)], "csv")


def ingest_excel(store: LocalStore, path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ValueError(f"Excel source does not exist: {path}")
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, KeyError, OSError, ParseError, ValueError) as error:
        raise ValueError(f"Invalid Excel source: {path}") from error
    tables = []
    for sheet in workbook.worksheets:
        values = list(sheet.iter_rows(values_only=True))
        if not values or not any(values[0]):
            raise ValueError(f"Excel header row is required: {sheet.title}")
        headers = [str(value) if value is not None else "" for value in values[0]]
        rows = [
            {headers[index]: value for index, value in enumerate(row) if headers[index]}
            for row in values[1:]
            if any(value is not None for value in row)
        ]
        tables.append((sheet.title, headers, rows))
    return _ingest_tables(store, path, tables, "excel")


def _ingest_tables(
    store: LocalStore,
    path: Path,
    tables: list[tuple[str, list[str], list[dict[str, Any]]]],
    source_type: str,
) -> list[dict[str, Any]]:
    store.init()
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    document, section, chunk = make_document(
        path,
        source_type,
        text=path.name,
        source_key=path.name,
    )
    graph = GraphRecords(documents=[document], sections=[section], chunks=[chunk])
    records = []
    for table_name, headers, rows in tables:
        table = artifact_for(table_name, "Table", document.document_id, aliases)
        graph.artifacts.append(table)
        records.append(
            {
                "artifact_id": table.artifact_id,
                "artifact_type": "Table",
                "display_name": table_name,
                "headers": headers,
                "rows": rows,
                "source": path.as_posix(),
            }
        )
        for header in headers:
            column = artifact_for(f"{table_name}.{header}", "Column", document.document_id, aliases)
            entity = entity_for(header, document.document_id, aliases)
            graph.artifacts.append(column)
            graph.entities.append(entity)
            relation, evidence = relation_with_evidence(
                source_id=column.artifact_id,
                target_id=entity.entity_id,
                relation_type="DEFINES",
                document=document,
                section_id=section.section_id,
                chunk_id=chunk.chunk_id,
                line_number=1,
                quote=header,
            )
            graph.relations.append(relation)
            graph.evidence.append(evidence)
    store.merge_graph(**graph.__dict__)
    return records
