from __future__ import annotations

import json

from pydantic import BaseModel, Field

from specimpact.models import utc_now
from specimpact.store import LocalStore


class ImpactDecision(BaseModel):
    impact_id: str
    change_id: str
    candidate_node_id: str
    status: str = "unreviewed"
    reason: str = ""
    updated_at: str = Field(default_factory=utc_now)
    analysis_id: str | None = None
    decision_analysis_id: str | None = None
    case_ids: list[str] = Field(default_factory=list)
    needs_revalidation: bool = False


STATUSES = {
    "unreviewed",
    "accepted",
    "rejected",
    "needs_investigation",
    "implemented",
    "tested",
    "closed",
}


def set_impact_status(
    store: LocalStore,
    impact_id: str,
    status: str,
    reason: str = "",
) -> ImpactDecision:
    if status not in STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(STATUSES))}")
    decisions = store.read("impact_decisions", ImpactDecision)
    decision = next((item for item in decisions if item.impact_id == impact_id), None)
    if not decision:
        change_id, candidate = _split_impact_id(impact_id)
        decision = ImpactDecision(
            impact_id=impact_id,
            change_id=change_id,
            candidate_node_id=candidate,
        )
        decisions.append(decision)
    decision.status = status
    decision.reason = reason
    decision.updated_at = utc_now()
    if decision.analysis_id and status != "unreviewed":
        from specimpact.semantic.repository import AnalysisRepository, DecisionEvent

        repository = AnalysisRepository(store.root)
        for case_id in decision.case_ids:
            repository.decide(DecisionEvent(
                analysis_id=decision.analysis_id, case_id=case_id, actor="local-user",
                status=status, reason=reason or "Explicit local review action",
            ))
        decision.decision_analysis_id = decision.analysis_id
        decision.needs_revalidation = False
    store.write("impact_decisions", decisions)
    return decision


def list_impacts(store: LocalStore, change_id: str | None = None) -> str:
    decisions = store.read("impact_decisions", ImpactDecision)
    if change_id:
        decisions = [item for item in decisions if item.change_id == change_id]
    return json.dumps([item.model_dump() for item in decisions], ensure_ascii=False, indent=2)


def ensure_decisions_for_report(
    store: LocalStore,
    change_id: str,
    candidate_ids: list[str],
    analysis_id: str | None = None,
) -> None:
    decisions = store.read("impact_decisions", ImpactDecision)
    existing = {item.impact_id for item in decisions}
    for candidate_id in candidate_ids:
        impact_id = impact_id_for(change_id, candidate_id)
        if impact_id not in existing:
            decisions.append(
                ImpactDecision(
                    impact_id=impact_id,
                    change_id=change_id,
                    candidate_node_id=candidate_id,
                )
            )
    if analysis_id:
        from specimpact.semantic.repository import AnalysisRepository

        _, _, analysis = AnalysisRepository(store.root).load(analysis_id)
        for decision in decisions:
            if decision.change_id == change_id and decision.candidate_node_id in candidate_ids:
                decision.analysis_id = analysis_id
                decision.case_ids = [c.case_id for c in analysis.cases
                                     if c.artifact_id == decision.candidate_node_id]
                decision.needs_revalidation = decision.status != "unreviewed" and (
                    decision.decision_analysis_id != analysis_id
                )
    store.write("impact_decisions", decisions)


def impact_id_for(change_id: str, candidate_id: str) -> str:
    return f"impact.{change_id}.{candidate_id}".replace(" ", "_")


def _split_impact_id(impact_id: str) -> tuple[str, str]:
    parts = impact_id.split(".")
    if len(parts) >= 4 and parts[0] == "impact":
        return ".".join(parts[1:3]), ".".join(parts[3:])
    return "change.unknown", impact_id
