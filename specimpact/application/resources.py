from __future__ import annotations

from typing import Any

from specimpact.application.contracts import Project
from specimpact.application.service import (
    design_documents_data,
    graph_data,
    project_overview,
    store_for,
)
from specimpact.dirty_excel.models import DirtyRegion
from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.impact_management.decision_store import ImpactDecision
from specimpact.models import Evidence

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


class ResourceReader:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.store = store_for(project)

    def project_resource(self, project_id: str) -> dict[str, Any]:
        self._require_project(project_id)
        if not (self.store.root / "config.yml").is_file():
            return {
                "project": self.project.model_dump(),
                "onboarding_required": True,
                "next_command": f'cd "{self.project.path}" && specimpact init',
            }
        return {**project_overview(self.project), "onboarding_required": False}

    def source_resource(
        self,
        source_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        self._require_initialized()
        documents = design_documents_data(self.project, evidence_ids=[])["documents"]
        source = next(
            (
                item
                for item in documents
                if source_id in {item.get("document_id"), item.get("file")}
            ),
            None,
        )
        if not source:
            raise KeyError(f"Unknown source: {source_id}")
        items = [
            *({"kind": "row", **item} for item in source.get("rows", [])),
            *({"kind": "cell", **item} for item in source.get("cells", [])),
            *({"kind": "region", **item} for item in source.get("regions", [])),
        ]
        metadata = {
            key: value
            for key, value in source.items()
            if key not in {"rows", "cells", "regions", "evidence"}
        }
        return {"source": metadata, **_page(items, cursor=cursor, limit=limit)}

    def evidence_resource(self, evidence_id: str) -> dict[str, Any]:
        self._require_initialized()
        evidence = next(
            (
                item
                for item in self.store.read("evidence", Evidence)
                if item.evidence_id == evidence_id
            ),
            None,
        )
        if not evidence:
            raise KeyError(f"Unknown evidence: {evidence_id}")
        return evidence.model_dump()

    def change_resource(self, change_id: str) -> dict[str, Any]:
        self._require_initialized()
        atoms = [
            item.model_dump()
            for item in self.store.read("change_atoms", ChangeAtom)
            if item.change_id == change_id
        ]
        if not atoms:
            raise KeyError(f"Unknown change: {change_id}")
        return {"change_id": change_id, "change_atoms": atoms}

    def impact_resource(self, impact_id: str) -> dict[str, Any]:
        self._require_initialized()
        impact = next(
            (
                item
                for item in self.store.read("impact_decisions", ImpactDecision)
                if item.impact_id == impact_id
            ),
            None,
        )
        if not impact:
            raise KeyError(f"Unknown impact: {impact_id}")
        return impact.model_dump()

    def graph_resource(
        self,
        node_id: str,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        self._require_initialized()
        graph = graph_data(self.project)
        node = next((item for item in graph["nodes"] if item["data"]["id"] == node_id), None)
        if not node:
            raise KeyError(f"Unknown graph node: {node_id}")
        edges = [
            item
            for item in graph["edges"]
            if node_id in {item["data"]["source"], item["data"]["target"]}
        ]
        return {"node": node, **_page(edges, cursor=cursor, limit=limit)}

    def regions_resource(
        self,
        *,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict[str, Any]:
        self._require_initialized()
        items = [
            {
                "region_id": item.region_id,
                "workbook_id": item.workbook_id,
                "sheet_id": item.sheet_id,
                "sheet_name": item.sheet_name,
                "range": item.range,
                "region_type": item.region_type,
                "evidence_ids": item.evidence_ids,
                "rendered_length": len(item.rendered_text),
            }
            for item in self.store.read("dirty_regions", DirtyRegion)
            if item.region_type != "revision_history"
        ]
        return _page(items, cursor=cursor, limit=limit)

    def region_resource(self, region_id: str) -> dict[str, Any]:
        self._require_initialized()
        region = next(
            (
                item
                for item in self.store.read("dirty_regions", DirtyRegion)
                if item.region_id == region_id
            ),
            None,
        )
        if not region:
            raise KeyError(f"Unknown Dirty Excel region: {region_id}")
        return {
            "region_id": region.region_id,
            "workbook_id": region.workbook_id,
            "sheet_id": region.sheet_id,
            "sheet_name": region.sheet_name,
            "range": region.range,
            "region_type": region.region_type,
            "evidence_ids": region.evidence_ids,
            "rendered_length": len(region.rendered_text),
            "content_withheld": True,
        }

    def _require_project(self, project_id: str) -> None:
        if project_id != self.project.project_id:
            raise KeyError(f"Unknown project: {project_id}")

    def _require_initialized(self) -> None:
        if not (self.store.root / "config.yml").is_file():
            raise ValueError("SpecImpact is not initialized; read the onboarding prompt first")


def _page(items: list[Any], *, cursor: str | None, limit: int) -> dict[str, Any]:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    try:
        offset = int(cursor or "0")
    except ValueError as error:
        raise ValueError("Invalid resource cursor") from error
    if offset < 0 or offset > len(items):
        raise ValueError("Invalid resource cursor")
    end = min(offset + limit, len(items))
    return {
        "items": items[offset:end],
        "cursor": str(offset),
        "next_cursor": str(end) if end < len(items) else None,
        "total": len(items),
        "limit": limit,
    }
