from __future__ import annotations

import hashlib
import re
from typing import Any

from specimpact.dirty_excel.models import DirtyCell, DirtyRegion
from specimpact.graphrag import LLMClient
from specimpact.llm_graph.schemas import ExtractedEdge, ExtractedNode, RegionExtractionResult


def extract_region_with_llm(
    region: DirtyRegion,
    cells: list[DirtyCell],
    client: LLMClient | None,
) -> RegionExtractionResult:
    if client is None:
        return extract_region_heuristic(region, cells)
    payload = {
        "region_id": region.region_id,
        "sheet": region.sheet_name,
        "range": region.range,
        "region_type_hint": region.region_type,
        "cells_markdown": region.rendered_text,
        "allowed_evidence_ids": region.evidence_ids,
    }
    result = client.structured("dirty_excel_region_extraction", payload, RegionExtractionResult)
    return _clean_result(result, region)


def extract_region_heuristic(region: DirtyRegion, cells: list[DirtyCell]) -> RegionExtractionResult:
    matrix = _matrix(region, cells)
    if not matrix:
        return RegionExtractionResult(region_id=region.region_id, nodes=[], edges=[])
    header_index, headers = _header(matrix)
    rows = matrix[header_index + 1 :] if header_index is not None else matrix[1:]
    nodes: dict[str, ExtractedNode] = {}
    edges: list[ExtractedEdge] = []

    def node(node_type: str, name: str, evidence_ids: list[str], rationale: str) -> str:
        key = f"{node_type}:{name}"
        if key not in nodes:
            nodes[key] = ExtractedNode(
                temp_id=f"n_{_short_hash(region.region_id + key)}",
                node_type=node_type,  # type: ignore[arg-type]
                display_name=name,
                canonical_hint=_canonical_hint(name),
                evidence_ids=sorted(set(evidence_ids)),
                rationale=rationale,
            )
        else:
            nodes[key].evidence_ids = sorted({*nodes[key].evidence_ids, *evidence_ids})
        return nodes[key].temp_id

    def edge(
        source: str,
        relation: str,
        target: str,
        evidence_ids: list[str],
        rationale: str,
    ) -> None:
        key = f"{source}:{relation}:{target}:{','.join(evidence_ids)}"
        edges.append(
            ExtractedEdge(
                temp_id=f"e_{_short_hash(region.region_id + key)}",
                source_temp_id=source,
                relation_type=relation,  # type: ignore[arg-type]
                target_temp_id=target,
                evidence_ids=sorted(set(evidence_ids)),
                inference_level="explicit",
                rationale=rationale,
            )
        )

    for row in rows:
        values = _row_dict(headers, row)
        evidence_ids = [item["evidence_id"] for item in row if item.get("evidence_id")]
        if not any(values.values()):
            continue
        if region.region_type == "screen_item_table":
            screen_name = (
                _first(values, "画面名", "screen_name", "col_2")
                or _clean_sheet_name(region.sheet_name)
            )
            field_name = _first(
                values, "項目名", "物理名", "item_name", "field", "col_5", "col_4"
            )
            api_name = _first(values, "呼び出すAPI", "API", "api", "col_10")
            if screen_name and field_name:
                screen = node("Screen", screen_name, evidence_ids, "screen region row")
                field = node("ScreenField", field_name, evidence_ids, "screen item row")
                edge(screen, "DISPLAYS", field, evidence_ids, "screen displays field")
            if screen_name and api_name:
                screen = node("Screen", screen_name, evidence_ids, "screen region row")
                api = node("API", api_name, evidence_ids, "screen API reference")
                edge(screen, "CALLS", api, evidence_ids, "screen calls API")
        elif region.region_type == "api_mapping_table":
            api_name = (
                _first(values, "API名", "api_name", "API", "col_2")
                or _clean_sheet_name(region.sheet_name)
            )
            field_name = _first(
                values, "物理名", "項目名", "field", "リクエスト項目", "col_6", "col_5"
            )
            direction = (_first(values, "区分", "direction", "col_4") or "request").lower()
            if api_name and field_name:
                api = node("API", api_name, evidence_ids, "API mapping row")
                field = node("APIField", field_name, evidence_ids, "API field row")
                relation = (
                    "RESPONSE_FIELD"
                    if "response" in direction or "レスポンス" in direction
                    else "REQUEST_FIELD"
                )
                edge(api, relation, field, evidence_ids, "API field relation")
        elif region.region_type == "db_mapping_table":
            table_name = (
                _first(values, "テーブル名", "table_name", "col_1")
                or _clean_sheet_name(region.sheet_name)
            )
            column_name = _first(values, "カラム名", "column_name", "物理名", "col_3")
            logical_name = _first(
                values, "カラム論理名", "logical_name", "項目名", "col_4"
            )
            if table_name and column_name:
                table = node("DBTable", table_name, evidence_ids, "DB table row")
                column = node(
                    "DBColumn",
                    f"{table_name}.{column_name}",
                    evidence_ids,
                    "DB column row",
                )
                edge(table, "contains", column, evidence_ids, "table contains column")
                field = node(
                    "ScreenField",
                    logical_name or column_name,
                    evidence_ids,
                    "business field",
                )
                edge(column, "DEFINES", field, evidence_ids, "column defines field")
        elif region.region_type == "validation_block":
            name = _first(values, "チェック名", "チェックID", "validation", "col_2", "col_1")
            target = _first(values, "対象項目", "物理名", "項目名", "target", "col_5", "col_4")
            if name and target:
                validation = node("ValidationRule", name, evidence_ids, "validation row")
                field = node("ScreenField", target, evidence_ids, "validation target field")
                edge(validation, "VALIDATES", field, evidence_ids, "validation validates field")
        elif region.region_type == "external_if_table":
            if_name = (
                _first(values, "IF名", "if_name", "外部IF", "col_2")
                or _clean_sheet_name(region.sheet_name)
            )
            field_name = _first(
                values, "物理名", "項目名", "送信項目", "受信項目", "field", "col_5", "col_4"
            )
            if if_name and field_name:
                external = node("ExternalIF", if_name, evidence_ids, "external IF row")
                field = node("APIField", field_name, evidence_ids, "external field row")
                edge(external, "SENDS", field, evidence_ids, "external IF sends field")
        elif region.region_type == "test_case_table":
            test_name = _first(
                values, "テスト名", "テストケースID", "試験ID", "test", "col_2", "col_1"
            )
            target = _first(values, "対象項目", "確認観点", "項目名", "target", "col_4")
            if test_name and target:
                test = node("TestCase", test_name, evidence_ids, "test row")
                field = node("ScreenField", target, evidence_ids, "test target")
                edge(test, "COVERS", field, evidence_ids, "test covers field")
    return RegionExtractionResult(
        region_id=region.region_id,
        nodes=list(nodes.values()),
        edges=edges,
        unresolved_mentions=_unresolved(region.rendered_text),
    )


def _clean_result(result: RegionExtractionResult, region: DirtyRegion) -> RegionExtractionResult:
    allowed = set(region.evidence_ids)
    result.nodes = [
        node
        for node in result.nodes
        if node.evidence_ids and all(evidence_id in allowed for evidence_id in node.evidence_ids)
    ]
    node_ids = {node.temp_id for node in result.nodes}
    result.edges = [
        edge
        for edge in result.edges
        if edge.source_temp_id in node_ids
        and edge.target_temp_id in node_ids
        and edge.evidence_ids
        and all(evidence_id in allowed for evidence_id in edge.evidence_ids)
    ]
    result.region_id = region.region_id
    return result


def _matrix(region: DirtyRegion, cells: list[DirtyCell]) -> list[list[dict[str, Any]]]:
    by_pos = {
        (cell.row, cell.column): cell
        for cell in cells
        if cell.sheet_id == region.sheet_id
        and region.start_row <= cell.row <= region.end_row
        and region.start_column <= cell.column <= region.end_column
    }
    rows: list[list[dict[str, Any]]] = []
    for row in range(region.start_row, region.end_row + 1):
        rendered = []
        for column in range(region.start_column, region.end_column + 1):
            cell = by_pos.get((row, column))
            rendered.append(
                {
                    "value": cell.value.strip() if cell and cell.value else "",
                    "evidence_id": cell.evidence_id if cell else "",
                }
            )
        rows.append(rendered)
    return rows


def _header(matrix: list[list[dict[str, Any]]]) -> tuple[int | None, list[str]]:
    best_index = None
    best_values: list[str] = []
    for index, row in enumerate(matrix[:8]):
        values = [str(cell["value"]).strip() for cell in row]
        non_empty = [value for value in values if value]
        if len(non_empty) > max(1, len([value for value in best_values if value])):
            best_index = index
            best_values = values
    if best_index is None:
        return None, []
    return best_index, [value or f"col_{index + 1}" for index, value in enumerate(best_values)]


def _row_dict(headers: list[str], row: list[dict[str, Any]]) -> dict[str, str]:
    result = {}
    for index, header in enumerate(headers):
        if index >= len(row):
            continue
        value = str(row[index].get("value") or "").strip()
        result[f"col_{index + 1}"] = value
        if header:
            result[header] = value
    return result


def _first(values: dict[str, str], *names: str) -> str:
    lowered = {key.casefold(): value for key, value in values.items()}
    for name in names:
        if values.get(name):
            return values[name]
        folded = name.casefold()
        for key, value in lowered.items():
            if folded in key and value:
                return value
    return ""


def _unresolved(text: str) -> list[str]:
    return sorted(set(re.findall(r"同上|上記と同じ|別紙参照", text)))


def _canonical_hint(name: str) -> str | None:
    ascii_name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return ascii_name or None


def _clean_sheet_name(name: str) -> str:
    return re.sub(r"(定義書|一覧|シート|項目|設計書)$", "", name).strip() or name


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
