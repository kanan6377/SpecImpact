from __future__ import annotations

from pathlib import Path
from typing import Callable

from specimpact.graphrag import client_from_config, ensure_llm_consent
from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.impact_hypothesis import build_impact_hypotheses
from specimpact.impact_management.impact_retrieval import retrieve_impacts
from specimpact.impact_management.report_store import persist_analysis_report
from specimpact.models import ChangeRequest, Report
from specimpact.store import LocalStore


def analyze_change_llm_first(
    store: LocalStore,
    change_path: Path,
    *,
    yes: bool = False,
    no_llm: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> Report:
    extraction = parse_change_atoms(store, change_path)
    atoms = extraction.change_atoms
    body = change_path.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("#")),
        change_path.stem,
    )
    retrieved = retrieve_impacts(store, atoms)
    client = None if no_llm else client_from_config(store)
    if client:
        ensure_llm_consent(
            client,
            purpose="impact_hypothesis",
            chunk_count=len(retrieved),
            yes=yes,
            confirm=confirm,
        )
    impacts = build_impact_hypotheses(
        store,
        atoms,
        retrieved,
        use_llm=bool(client),
        llm_client=client,
    )
    change = ChangeRequest(
        change_id=extraction.change_id,
        title=title,
        path=change_path.as_posix(),
        body=body,
        changed_entity_ids=sorted({term for atom in atoms for term in atom.target_terms}),
    )
    return persist_analysis_report(
        store,
        change=change,
        impacts=impacts,
        atom_ids=[atom.atom_id for atom in atoms],
        retrieved_paths=[
            {
                "node_id": path.node_id,
                "relation_ids": [relation.relation_id for relation in path.relations],
                "evidence_ids": path.evidence_ids,
            }
            for path in retrieved
        ],
        llm_provider=getattr(client, "provider", None),
        llm_model=getattr(client, "model", None),
    )
