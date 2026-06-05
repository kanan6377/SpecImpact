from __future__ import annotations

import hashlib
from pathlib import Path

from specimpact.dirty_excel.models import DirtyRegion
from specimpact.extraction import GraphRecords, make_document
from specimpact.models import Chunk, Document, Section


def document_graph_for_regions(
    path: Path,
    regions: list[DirtyRegion],
    *,
    source_key: str,
) -> tuple[GraphRecords, dict[str, Chunk], Document]:
    text = "\n\n".join(region.rendered_text for region in regions) or path.name
    document, _, _ = make_document(path, "dirty_excel", text=text, source_key=source_key)
    sections: list[Section] = []
    chunks: list[Chunk] = []
    by_region: dict[str, Chunk] = {}
    line = 1
    for index, region in enumerate(regions, start=1):
        rendered_lines = max(1, len(region.rendered_text.splitlines()))
        suffix = _short_hash(region.region_id)
        section = Section(
            section_id=f"sec.{suffix}",
            document_id=document.document_id,
            heading=f"{region.sheet_name} {region.range}",
            level=1,
            line_start=line,
            line_end=line + rendered_lines - 1,
        )
        chunk = Chunk(
            chunk_id=f"chunk.{suffix}",
            document_id=document.document_id,
            section_id=section.section_id,
            text=region.rendered_text,
            line_start=section.line_start,
            line_end=section.line_end,
        )
        sections.append(section)
        chunks.append(chunk)
        by_region[region.region_id] = chunk
        line += rendered_lines + (2 if index < len(regions) else 0)
    return GraphRecords(documents=[document], sections=sections, chunks=chunks), by_region, document


def region_evidence_id(region_id: str, relation_key: str) -> str:
    return f"ev.{_short_hash(region_id + '|' + relation_key)}"


def region_quote(region: DirtyRegion, *, max_length: int = 2000) -> str:
    body = " / ".join(
        line
        for line in region.rendered_text.splitlines()
        if line and not line.startswith("| ---")
    )
    quote = f"[{region.sheet_name}!{region.range}] {body}"
    return quote[:max_length]


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
