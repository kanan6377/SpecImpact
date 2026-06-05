from __future__ import annotations

from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.impact_management.impact_retrieval import RetrievedPath
from specimpact.llm_graph.verifier import classify_impact
from specimpact.models import Artifact, Impact
from specimpact.store import LocalStore

PRIORITY_STRENGTH = {
    "must_review": "strong",
    "should_review": "medium",
    "may_review": "weak",
    "hidden": "none",
}
PRIORITY_ORDER = {"must_review": 0, "should_review": 1, "may_review": 2, "hidden": 3}


def build_impact_hypotheses(
    store: LocalStore,
    atoms: list[ChangeAtom],
    retrieved: list[RetrievedPath],
) -> list[Impact]:
    artifacts = {item.artifact_id: item for item in store.read("artifacts", Artifact)}
    impacts = []
    for path in retrieved:
        artifact = artifacts.get(path.node_id)
        if not artifact:
            continue
        atom = _best_atom(atoms, path)
        priority, verifier_reason = classify_impact(
            store,
            path.relations,
            path.evidence_ids,
            atom.target_terms,
            atom.before,
        )
        if priority == "hidden":
            continue
        impacts.append(
            Impact(
                artifact_id=artifact.artifact_id,
                display_name=artifact.display_name,
                artifact_type=artifact.artifact_type,
                review_priority=priority,
                evidence_strength=PRIORITY_STRENGTH[priority],
                match_type="exact" if priority == "must_review" else "semantic",
                relation_distance=len(path.relations),
                rule_assessment="explicit_relation"
                if any(relation.polarity == "explicit" for relation in path.relations)
                else "inferred_relation",
                reason=_reason(atom, verifier_reason, path),
                relation_paths=[_render_path(atom, path)],
                evidence_ids=path.evidence_ids,
                relation_statuses=sorted({relation.status for relation in path.relations}),
                needs_review=True,
            )
        )
    return sorted(
        impacts,
        key=lambda item: (PRIORITY_ORDER[item.review_priority], item.artifact_id),
    )


def _best_atom(atoms: list[ChangeAtom], _path: RetrievedPath) -> ChangeAtom:
    return atoms[0]


def _reason(atom: ChangeAtom, verifier_reason: str, path: RetrievedPath) -> str:
    target = ", ".join(atom.target_terms)
    change = ""
    if atom.before or atom.after:
        change = f" ({atom.before or '?'} -> {atom.after or '?'})"
    relation_types = " -> ".join(relation.relation_type for relation in path.relations)
    return f"{target}{change}: {verifier_reason} Relation path: {relation_types}."


def _render_path(atom: ChangeAtom, path: RetrievedPath) -> str:
    target = ",".join(atom.target_terms)
    parts = [f"change:{target}"]
    current = ""
    for relation in path.relations:
        current = f"{relation.source_id} -{relation.relation_type}-> {relation.target_id}"
        parts.append(current)
    return " <- ".join(parts)
