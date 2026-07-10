from __future__ import annotations

import json
from uuid import uuid4

from specimpact.impact_management.decision_store import ensure_decisions_for_report
from specimpact.models import ChangeRequest, Impact, Report
from specimpact.schema_validation import validate_report
from specimpact.store import LocalStore


def persist_analysis_report(
    store: LocalStore,
    *,
    change: ChangeRequest,
    impacts: list[Impact],
    atom_ids: list[str],
    retrieved_paths: list[dict],
    llm_provider: str | None,
    llm_model: str | None,
) -> Report:
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
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "atom_ids": atom_ids,
            "retrieved_paths": retrieved_paths,
            "impact_ids": [impact.artifact_id for impact in impacts],
        },
    )
    from specimpact.core import render_markdown

    store.write_text(run_dir / "report.md", render_markdown(report, store))
    ensure_decisions_for_report(store, change.change_id, [impact.artifact_id for impact in impacts])
    store.write_text(store.root / "latest_run", run_id)
    _append_review_session(
        store,
        run_id=run_id,
        change_id=change.change_id,
        llm_provider=llm_provider,
        llm_model=llm_model,
        retrieved_count=len(retrieved_paths),
        impact_count=len(impacts),
    )
    return report


def _append_review_session(
    store: LocalStore,
    *,
    run_id: str,
    change_id: str,
    llm_provider: str | None,
    llm_model: str | None,
    retrieved_count: int,
    impact_count: int,
) -> None:
    path = store.root / "review_sessions.jsonl"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    row = {
        "run_id": run_id,
        "change_id": change_id,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "retrieved_count": retrieved_count,
        "impact_count": impact_count,
    }
    store.write_text(path, existing + json.dumps(row, ensure_ascii=False) + "\n")
