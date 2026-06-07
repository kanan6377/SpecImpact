from __future__ import annotations

import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from specimpact.graphrag import client_from_config, ensure_llm_consent
from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.decision_store import ensure_decisions_for_report
from specimpact.impact_management.impact_hypothesis import build_impact_hypotheses
from specimpact.impact_management.impact_retrieval import retrieve_impacts
from specimpact.models import ChangeRequest, Report
from specimpact.schema_validation import validate_report
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
    run_id = uuid4().hex[:12]
    report = Report(run_id=run_id, change=change, impacts=impacts)
    run_dir = store.root / "runs" / run_id
    store.write_json(run_dir / "change_request.json", change.model_dump())
    store.write_text(
        run_dir / "candidates.jsonl",
        "".join(
            json.dumps(impact.model_dump(exclude_none=True), ensure_ascii=False) + "\n"
            for impact in impacts
        ),
    )
    store.write_json(run_dir / "impacts.json", report.grouped())
    report_json = {"run_id": run_id, "change": change.model_dump(), **report.grouped()}
    validate_report(report_json)
    store.write_json(run_dir / "report.json", report_json)
    store.write_json(
        run_dir / "review_replay.json",
        {
            "run_id": run_id,
            "change_id": change.change_id,
            "llm_provider": getattr(client, "provider", None),
            "llm_model": getattr(client, "model", None),
            "atom_ids": [atom.atom_id for atom in atoms],
            "retrieved_paths": [
                {
                    "node_id": path.node_id,
                    "relation_ids": [relation.relation_id for relation in path.relations],
                    "evidence_ids": path.evidence_ids,
                }
                for path in retrieved
            ],
            "impact_ids": [impact.artifact_id for impact in impacts],
        },
    )
    from specimpact.core import render_markdown

    store.write_text(run_dir / "report.md", render_markdown(report, store))
    ensure_decisions_for_report(store, change.change_id, [impact.artifact_id for impact in impacts])
    store.write_text(store.root / "latest_run", run_id)
    _append_review_session(store, run_id, change.change_id, client, len(retrieved), len(impacts))
    return report


def _append_review_session(
    store: LocalStore,
    run_id: str,
    change_id: str,
    client,
    retrieved_count: int,
    impact_count: int,
) -> None:
    path = store.root / "review_sessions.jsonl"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    row = {
        "run_id": run_id,
        "change_id": change_id,
        "llm_provider": getattr(client, "provider", None),
        "llm_model": getattr(client, "model", None),
        "retrieved_count": retrieved_count,
        "impact_count": impact_count,
    }
    store.write_text(path, existing + json.dumps(row, ensure_ascii=False) + "\n")
