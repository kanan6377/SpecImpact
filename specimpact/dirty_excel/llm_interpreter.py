from __future__ import annotations

from specimpact.dirty_excel.models import DirtyCell, DirtyRegion
from specimpact.graphrag import LLMClient
from specimpact.llm_graph.extraction import extract_region_with_llm
from specimpact.llm_graph.schemas import RegionExtractionResult


def interpret_region(
    region: DirtyRegion,
    cells: list[DirtyCell],
    client: LLMClient | None,
) -> RegionExtractionResult:
    return extract_region_with_llm(region, cells, client)
