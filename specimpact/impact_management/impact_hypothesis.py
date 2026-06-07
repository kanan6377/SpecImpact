from __future__ import annotations

from specimpact.graphrag import LLMClient, client_from_config
from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.impact_management.impact_retrieval import RetrievedPath
from specimpact.llm_graph.schemas import ImpactHypothesisLLMResult
from specimpact.llm_graph.verifier import classify_impact
from specimpact.models import Artifact, Evidence, Impact
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
    *,
    use_llm: bool = False,
    llm_client: LLMClient | None = None,
) -> list[Impact]:
    artifacts = {item.artifact_id: item for item in store.read("artifacts", Artifact)}
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    client = llm_client or (client_from_config(store) if use_llm else None)
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
            change_property=atom.property,
            artifact_type=artifact.artifact_type,
        )
        if priority == "hidden":
            continue
        llm_result = _llm_hypothesis(client, artifact, atom, path, evidence)
        evidence_ids = (
            [evidence_id for evidence_id in llm_result.evidence_ids if evidence_id in evidence]
            if llm_result
            else path.evidence_ids
        ) or path.evidence_ids
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
                reason=llm_result.reason if llm_result and llm_result.reason else _reason(
                    atom,
                    verifier_reason,
                    path,
                ),
                relation_paths=[_render_path(atom, path)],
                evidence_ids=evidence_ids,
                relation_statuses=sorted({relation.status for relation in path.relations}),
                needs_review=True,
                llm_reason=llm_result.reason if llm_result else None,
                impact_type=llm_result.impact_type if llm_result else _default_impact_type(atom),
                required_actions=llm_result.required_actions
                if llm_result
                else _default_actions(atom, artifact),
                warnings=llm_result.warnings if llm_result else [],
                uncertainty=llm_result.uncertainty if llm_result else priority,
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


def _llm_hypothesis(
    client: LLMClient | None,
    artifact: Artifact,
    atom: ChangeAtom,
    path: RetrievedPath,
    evidence: dict[str, Evidence],
) -> ImpactHypothesisLLMResult | None:
    if client is None:
        return None
    payload = {
        "change_atom": atom.model_dump(),
        "candidate_artifact": artifact.model_dump(),
        "relations": [relation.model_dump() for relation in path.relations],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "quote": evidence[evidence_id].quote,
                "file": evidence[evidence_id].source_location.file,
            }
            for evidence_id in path.evidence_ids
            if evidence_id in evidence
        ],
        "instruction": (
            "Act as a design impact analyst. Return concrete required_actions, warnings, "
            "impact_type, uncertainty, and evidence_ids. Use only supplied evidence."
        ),
    }
    return client.structured("impact_hypothesis", payload, ImpactHypothesisLLMResult)


def _default_impact_type(atom: ChangeAtom) -> str:
    if atom.operation == "change_constraint":
        return "constraint_change"
    if atom.operation:
        return atom.operation
    return "review"


def _default_actions(atom: ChangeAtom, artifact: Artifact) -> list[str]:
    target = ", ".join(atom.target_terms[:3]) or artifact.display_name
    if atom.property == "max_value" and atom.after:
        return [f"{artifact.display_name} の {target} 上限値を {atom.after} に合わせて確認する"]
    return [f"{artifact.display_name} が変更対象 {target} に関係するか確認する"]
