from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.decision_store import ensure_decisions_for_report
from specimpact.impact_management.impact_hypothesis import build_impact_hypotheses
from specimpact.impact_management.impact_retrieval import retrieve_impacts
from specimpact.models import ChangeRequest, Report
from specimpact.schema_validation import validate_report
from specimpact.store import LocalStore


def analyze_change_llm_first(store: LocalStore, change_path: Path) -> Report:
    extraction = parse_change_atoms(store, change_path)
    atoms = extraction.change_atoms
    body = change_path.read_text(encoding="utf-8")
    title = next(
        (line.lstrip("# ").strip() for line in body.splitlines() if line.startswith("#")),
        change_path.stem,
    )
    retrieved = retrieve_impacts(store, atoms)
    impacts = build_impact_hypotheses(store, atoms, retrieved)
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
    from specimpact.core import render_markdown

    store.write_text(run_dir / "report.md", render_markdown(report, store))
    ensure_decisions_for_report(store, change.change_id, [impact.artifact_id for impact in impacts])
    store.write_text(store.root / "latest_run", run_id)
    return report
