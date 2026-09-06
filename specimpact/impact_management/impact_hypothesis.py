from __future__ import annotations

from specimpact.graphrag import LLMClient, client_from_config
from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.impact_management.decision_store import ImpactDecision
from specimpact.impact_management.impact_retrieval import RetrievedPath
from specimpact.llm_graph.schemas import ImpactHypothesisLLMResult
from specimpact.llm_graph.verifier import classify_impact
from specimpact.models import Artifact, Evidence, Impact, Relation
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
    all_relations = store.read("relations", Relation)
    prior_decisions = _prior_decisions(store)
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
        priority = _apply_prior_decision(priority, prior_decisions.get(artifact.artifact_id))
        llm_result = _llm_hypothesis(
            client,
            artifact,
            atom,
            path,
            evidence,
            all_relations,
            prior_decisions,
        )
        if llm_result and llm_result.review_priority_suggestion:
            priority = _apply_llm_priority(priority, llm_result.review_priority_suggestion)
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


def _best_atom(atoms: list[ChangeAtom], path: RetrievedPath) -> ChangeAtom:
    if path.atom_id:
        return next(atom for atom in atoms if atom.atom_id == path.atom_id)
    if len(atoms) == 1:
        return atoms[0]
    raise ValueError("Multiple changes require an operation-bound retrieval path")


def _prior_decisions(store: LocalStore) -> dict[str, str]:
    result: dict[str, str] = {}
    for decision in store.read("impact_decisions", ImpactDecision):
        if decision.status in {"accepted", "rejected"}:
            result[decision.candidate_node_id] = decision.status
    return result


def _apply_prior_decision(priority: str, status: str | None) -> str:
    if status == "accepted" and priority == "may_review":
        return "should_review"
    if status == "rejected" and priority == "must_review":
        return "should_review"
    if status == "rejected" and priority == "should_review":
        return "may_review"
    return priority


def _apply_llm_priority(verifier_priority: str, suggestion: str) -> str:
    """Allow LLM to lower noise, never to exceed verifier grounding."""
    if PRIORITY_ORDER.get(suggestion, 99) > PRIORITY_ORDER.get(verifier_priority, 99):
        return suggestion
    return verifier_priority


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
    for relation in path.relations:
        parts.append(f"{relation.source_id} -{relation.relation_type}-> {relation.target_id}")
    return " <- ".join(parts)


def _llm_hypothesis(
    client: LLMClient | None,
    artifact: Artifact,
    atom: ChangeAtom,
    path: RetrievedPath,
    evidence: dict[str, Evidence],
    all_relations: list[Relation],
    prior_decisions: dict[str, str],
) -> ImpactHypothesisLLMResult | None:
    if client is None:
        return None
    payload = {
        "change_atom": atom.model_dump(),
        "candidate_artifact": artifact.model_dump(),
        "path_relations": [relation.model_dump() for relation in path.relations],
        "candidate_subgraph": _candidate_subgraph(path, artifact, evidence, all_relations),
        "prior_decisions": [
            {"candidate_node_id": node_id, "status": status}
            for node_id, status in sorted(prior_decisions.items())
            if node_id == artifact.artifact_id or node_id in _path_node_ids(path)
        ],
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
            "Act as a Japanese SIer design impact analyst. Return concrete Japanese "
            "required_actions, warnings, impact_type, uncertainty, review_priority_suggestion, "
            "and evidence_ids. Use only supplied evidence. Do not suggest must_review unless "
            "direct evidence and a graph path support the candidate. For max/min/length changes, "
            "include validation, API, DB, external IF, and boundary test actions when supported."
        ),
    }
    return client.structured("impact_hypothesis", payload, ImpactHypothesisLLMResult)


def _candidate_subgraph(
    path: RetrievedPath,
    artifact: Artifact,
    evidence: dict[str, Evidence],
    all_relations: list[Relation],
) -> dict[str, object]:
    node_ids = _path_node_ids(path) | {artifact.artifact_id}
    neighbor_relations = [*path.relations]
    seen = {relation.relation_id for relation in neighbor_relations}
    neighbor_relations.extend(
        relation
        for relation in all_relations
        if relation.source_id in node_ids or relation.target_id in node_ids
        if relation.relation_id not in seen
    )
    neighbor_relations = neighbor_relations[:40]
    evidence_ids = sorted(
        {
            evidence_id
            for relation in neighbor_relations
            for evidence_id in relation.evidence_ids
            if evidence_id in evidence
        }
        | set(path.evidence_ids)
    )
    return {
        "node_ids": sorted(
            {
                artifact.artifact_id,
                *node_ids,
                *[relation.source_id for relation in neighbor_relations],
                *[relation.target_id for relation in neighbor_relations],
            }
        ),
        "relations": [relation.model_dump() for relation in neighbor_relations],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "quote": evidence[evidence_id].quote,
                "file": evidence[evidence_id].source_location.file,
            }
            for evidence_id in evidence_ids
            if evidence_id in evidence
        ],
    }


def _path_node_ids(path: RetrievedPath) -> set[str]:
    nodes = {path.node_id}
    for relation in path.relations:
        nodes.add(relation.source_id)
        nodes.add(relation.target_id)
    return nodes


def _default_impact_type(atom: ChangeAtom) -> str:
    if atom.operation == "change_constraint":
        return "constraint_change"
    if atom.operation:
        return atom.operation
    return "review"


def _default_actions(atom: ChangeAtom, artifact: Artifact) -> list[str]:
    target = ", ".join(atom.target_terms[:3]) or artifact.display_name
    artifact_type = artifact.artifact_type.lower()
    if atom.property == "max_value" and atom.after:
        return [_action_for_artifact(artifact, target, f"上限値を {atom.after} に合わせて確認する")]
    if atom.property == "min_value" and atom.after:
        return [_action_for_artifact(artifact, target, f"下限値を {atom.after} に合わせて確認する")]
    if atom.property == "length" and atom.after:
        return [_action_for_artifact(artifact, target, f"桁数を {atom.after} に合わせて確認する")]
    if atom.property == "required":
        return [_action_for_artifact(artifact, target, "必須/任意条件を確認する")]
    if "test" in artifact_type:
        return [f"{artifact.display_name} のテスト観点が変更対象 {target} をカバーするか確認する"]
    return [f"{artifact.display_name} が変更対象 {target} に関係するか確認する"]


def _action_for_artifact(artifact: Artifact, target: str, action: str) -> str:
    artifact_type = artifact.artifact_type.lower()
    if "test" in artifact_type:
        return f"{artifact.display_name} の境界値テストを {target} の変更後条件に合わせて更新する"
    if "validation" in artifact_type:
        return f"{artifact.display_name} の {target} {action}"
    if "api" in artifact_type:
        return f"{artifact.display_name} の {target} API項目仕様と桁数/型を確認する"
    if "column" in artifact_type or "table" in artifact_type:
        return f"{artifact.display_name} の {target} DB定義、桁数、制約を確認する"
    if "external" in artifact_type:
        return f"{artifact.display_name} の {target} 外部IF送受信項目を確認する"
    if "screen" in artifact_type:
        return f"{artifact.display_name} の {target} 表示、入力、エラーメッセージを確認する"
    return f"{artifact.display_name} の {target} {action}"
