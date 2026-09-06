from __future__ import annotations

from specimpact.impact_management.change_atoms import ChangeAtom, _heuristic_atoms
from specimpact.models import ChangeRequest, Impact
from specimpact.semantic.kernel import AnalysisResult
from specimpact.semantic.repository import AnalysisRepository, capture
from specimpact.store import LocalStore

PRIORITIES = {"must_review": 0, "should_review": 1, "may_review": 2, "hidden": 3}


def record_analysis(
    store: LocalStore,
    change: ChangeRequest,
    run_id: str,
    impacts: list[Impact],
    atoms: list[ChangeAtom] | None = None,
) -> tuple[list[Impact], AnalysisResult]:
    atoms = atoms or _heuristic_atoms(change.change_id, change.body)
    source = capture(store, atoms)
    result = AnalysisRepository(store.root).save(source, report_id=run_id)
    artifacts = {a.artifact_id: a for a in source.artifacts}
    relations = {r.relation_id: r for r in source.relations}
    operations = {op.operation_id: op for op in source.operations}
    projected = {}
    for impact in impacts:
        current = projected.get(impact.artifact_id)
        if current is None:
            projected[impact.artifact_id] = impact.model_copy(deep=True)
            continue
        if PRIORITIES[impact.review_priority] < PRIORITIES[current.review_priority]:
            current.review_priority = impact.review_priority
            current.evidence_strength = impact.evidence_strength
        current.reason += " " + impact.reason
        for field in (
            "evidence_ids",
            "relation_paths",
            "relation_statuses",
            "required_actions",
            "warnings",
        ):
            setattr(
                current,
                field,
                list(
                    dict.fromkeys(
                        [
                            *getattr(current, field),
                            *getattr(impact, field),
                        ]
                    )
                ),
            )
    by_artifact: dict[str, list] = {}
    for case in result.cases:
        if operations[case.operation_id].property == "max_length":
            by_artifact.setdefault(case.artifact_id, []).append(case)
    for artifact_id, cases in by_artifact.items():
        # Older unlabeled properties remain visible as compatibility review candidates.
        if not any(c.assertion_ids for c in cases):
            continue
        cases.sort(key=lambda c: (PRIORITIES[c.review_priority], c.case_id))
        selected = cases[0]
        artifact = artifacts[artifact_id]
        paths = [p for c in cases for p in c.relation_paths]
        original = projected.get(artifact_id)
        projected[artifact_id] = Impact(
            artifact_id=artifact_id,
            display_name=artifact.display_name,
            artifact_type=artifact.artifact_type,
            review_priority=selected.review_priority,
            evidence_strength=selected.evidence_strength,
            match_type="exact",
            relation_distance=min((len(p) for p in paths), default=0),
            rule_assessment="explicit_relation",
            needs_review=True,
            reason=" ".join(f"[{c.operation_id}] {c.reason}" for c in cases),
            relation_paths=[" -> ".join(p) for p in paths],
            evidence_ids=sorted({eid for c in cases for eid in c.evidence_ids}),
            relation_statuses=sorted(
                {relations[r].status for p in paths for r in p if r in relations}
            ),
            impact_type=selected.outcome,
            required_actions=list(dict.fromkeys(a for c in cases for a in c.required_actions)),
            warnings=sorted({v for c in cases for v in c.verification.unresolved}),
            uncertainty="unresolved"
            if any(c.verification.unresolved for c in cases)
            else ("bounded_property_check"),
            llm_reason=original.llm_reason if original else None,
        )
    typed = {aid for aid, cases in by_artifact.items() if any(c.assertion_ids for c in cases)}
    for impact in projected.values():
        if impact.artifact_id not in typed:
            impact.warnings = list(
                dict.fromkeys(
                    [
                        *impact.warnings,
                        "legacy_candidate_not_a_verified_constraint_comparison",
                    ]
                )
            )
    # Disposable projection. The database remains authoritative and can regenerate this file.
    store.write_json(store.root / "runs" / run_id / "analysis.json", result.model_dump())
    return sorted(
        projected.values(), key=lambda i: (PRIORITIES[i.review_priority], i.artifact_id)
    ), result


def analysis_summary(store: LocalStore, run_id: str) -> dict | None:
    repository = AnalysisRepository(store.root)
    if not repository.path.exists():
        return None
    try:
        _, _, result = repository.load(run_id)
    except ValueError as error:
        if str(error).startswith("Unknown analysis"):
            return None
        raise
    return {
        "analysis_id": result.analysis_id,
        "schema_version": result.schema_version,
        "rule_version": result.rule_version,
        "coverage": result.coverage.model_dump(),
        "cases": [c.model_dump() for c in result.cases],
    }


def markdown_summary(result: AnalysisResult) -> str:
    coverage = result.coverage
    lines = [
        "",
        "## Specification analysis",
        "",
        f"- Analysis: {result.analysis_id}",
        f"- Rule version: {result.rule_version}",
        f"- Sources: {coverage.documents}; evidence: {coverage.evidence_records}; "
        f"labelled assertions: {coverage.assertions}",
        f"- Operations: {coverage.operations}; cases: {coverage.returned_cases}",
        "- Coverage describes the ingested inventory, not all possible system impacts.",
        "- Legacy candidates without a typed rule remain unverified review assistance.",
    ]
    lines.extend(f"- Gap: {g}" for g in coverage.gaps)
    lines.extend(f"- Truncated: {g}" for g in coverage.truncations)
    lines.extend(f"- Unmatched operation: {g}" for g in coverage.unmatched_operations)
    return "\n".join(lines) + "\n"
