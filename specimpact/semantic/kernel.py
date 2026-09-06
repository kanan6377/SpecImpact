from __future__ import annotations

from collections import deque
from typing import Literal

from pydantic import Field

from specimpact.models import Artifact, Document, Entity, Evidence, Relation
from specimpact.semantic.extraction import extract_assertions, mentions, normalize
from specimpact.semantic.models import ChangeOperation, Contract, SpecAssertion, content_id

RULE_VERSION = "length-contracts-1"
DIRECT = {
    "DEFINES",
    "REQUEST_FIELD",
    "RESPONSE_FIELD",
    "VALIDATES",
    "DISPLAYS",
    "defines",
    "validates",
    "displays",
    "accepts_input",
    "contains",
}
TRAVERSE = DIRECT | {
    "READS",
    "WRITES",
    "SENDS",
    "RECEIVES",
    "COVERS",
    "CALLS",
    "MENTIONS",
    "reads",
    "writes",
    "sends",
    "receives",
    "tested_by",
    "calls",
    "maps_to",
    "depends_on",
    "may_affect",
    "same_as",
}


class AnalysisInput(Contract):
    documents: list[Document]
    entities: list[Entity]
    artifacts: list[Artifact]
    relations: list[Relation]
    evidence: list[Evidence]
    operations: list[ChangeOperation]
    stale_evidence_ids: list[str] = Field(default_factory=list)
    source_gaps: list[str] = Field(default_factory=list)


class AnalysisLimits(Contract):
    max_depth: int = Field(default=4, ge=1, le=20)
    max_paths: int = Field(default=10000, ge=1)
    max_cases: int = Field(default=1000, ge=1)


class Verification(Contract):
    references_valid: bool = False
    identity_resolved: bool = False
    path_grounded: bool = False
    property_supported: bool = False
    units_comparable: bool = False
    rule_id: str = RULE_VERSION
    unresolved: list[str] = Field(default_factory=list)


class ImpactCase(Contract):
    case_id: str
    operation_id: str
    artifact_id: str
    subject_id: str
    assertion_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    relation_paths: list[list[str]] = Field(default_factory=list)
    outcome: Literal["inconsistency", "satisfied", "unresolved", "unsupported", "test_review"]
    review_priority: Literal["must_review", "should_review", "may_review"]
    evidence_strength: Literal["strong", "medium", "weak", "none"]
    reason: str
    required_actions: list[str] = Field(default_factory=list)
    verification: Verification


class AnalysisCoverage(Contract):
    documents: int
    evidence_records: int
    assertions: int
    operations: int
    examined_paths: int = 0
    returned_cases: int = 0
    excluded_relations: list[str] = Field(default_factory=list)
    unmatched_operations: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    truncations: list[str] = Field(default_factory=list)
    complete: bool = False


class AnalysisResult(Contract):
    schema_version: Literal["2"] = "2"
    rule_version: str = RULE_VERSION
    analysis_id: str
    assertions: list[SpecAssertion]
    cases: list[ImpactCase]
    coverage: AnalysisCoverage


def analyze(source: AnalysisInput, limits: AnalysisLimits | None = None) -> AnalysisResult:
    limits = limits or AnalysisLimits()
    operation_ids = [o.operation_id for o in source.operations]
    if len(operation_ids) != len(set(operation_ids)):
        raise ValueError("Duplicate operation IDs")
    found_mentions, assertions = extract_assertions(
        source.entities,
        source.relations,
        source.evidence,
        source.documents,
    )
    coverage = AnalysisCoverage(
        documents=len(source.documents),
        evidence_records=len(source.evidence),
        assertions=len(assertions),
        operations=len(source.operations),
        gaps=source.source_gaps[:],
    )
    document_ids = {d.document_id for d in source.documents}
    coverage.gaps.extend(
        f"missing_document:{e.document_id}"
        for e in source.evidence
        if e.document_id not in document_ids
    )
    coverage.gaps.extend(f"stale_evidence:{eid}" for eid in source.stale_evidence_ids)
    incoming: dict[str, list[Relation]] = {}
    for relation in sorted(source.relations, key=lambda r: r.relation_id):
        if relation.status == "rejected":
            coverage.excluded_relations.append(relation.relation_id)
        elif relation.relation_type in TRAVERSE:
            incoming.setdefault(relation.target_id, []).append(relation)
        else:
            coverage.gaps.append(f"unsupported_relation:{relation.relation_id}")
    artifacts = {a.artifact_id: a for a in source.artifacts}
    cases = []
    for op in sorted(source.operations, key=lambda o: o.operation_id):
        seeds = [
            e
            for e in source.entities
            if (not op.scope or e.scope == op.scope)
            and any(
                normalize(t) == normalize(n)
                for t in op.target_terms
                for n in [e.entity_id, e.display_name, e.canonical_name, *e.aliases]
            )
        ]
        ambiguous = len({e.scope for e in seeds}) > 1 or (
            len(seeds) > 1 and any(not e.scope for e in seeds)
        )
        if not seeds:
            coverage.unmatched_operations.append(op.operation_id)
        for seed in sorted(seeds, key=lambda e: e.entity_id):
            paths: dict[str, list[list[Relation]]] = {}
            queue = deque([(seed.entity_id, [], {seed.entity_id})])
            while queue:
                node, path, visited = queue.popleft()
                for edge in incoming.get(node, []):
                    if edge.source_id in visited:
                        continue
                    if coverage.examined_paths >= limits.max_paths:
                        coverage.truncations.append("max_paths")
                        queue.clear()
                        break
                    coverage.examined_paths += 1
                    next_path = [*path, edge]
                    if edge.source_id in artifacts:
                        paths.setdefault(edge.source_id, []).append(next_path)
                    if len(next_path) < limits.max_depth and edge.relation_type != "MENTIONS":
                        queue.append((edge.source_id, next_path, visited | {edge.source_id}))
                    elif incoming.get(edge.source_id):
                        coverage.truncations.append("max_depth")
            for artifact_id, candidate_paths in sorted(paths.items()):
                own = [
                    a
                    for a in assertions
                    if a.subject_id == seed.entity_id and a.artifact_id == artifact_id
                ]
                case = _case(
                    source, op, seed, artifacts[artifact_id], own, candidate_paths, not ambiguous
                )
                conflicting = any(
                    other.operation_id != op.operation_id
                    and other.scope == op.scope
                    and other.property == op.property
                    and other.after != op.after
                    and set(map(normalize, other.target_terms))
                    & set(map(normalize, op.target_terms))
                    for other in source.operations
                )
                if conflicting:
                    case.outcome = "unresolved"
                    case.review_priority = "should_review"
                    case.reason = "同じ対象の変更後条件が競合しています。"
                    case.verification.unresolved.append("conflicting_change_operations")
                cases.append(case)
            connected = {
                eid
                for group in paths.values()
                for path in group
                for edge in path
                for eid in edge.evidence_ids
            }
            for mention in found_mentions:
                if (
                    mention.entity_id == seed.entity_id
                    and mention.anchor.evidence_id not in connected
                ):
                    coverage.gaps.append(
                        f"disconnected_mention:{op.operation_id}:{mention.anchor.evidence_id}"
                    )
        # Independent source scan catches concepts not represented in the graph.
        if not seeds:
            for evidence in source.evidence:
                if any(mentions(evidence.quote, term) for term in op.target_terms):
                    coverage.gaps.append(
                        f"unmapped_source_match:{op.operation_id}:{evidence.evidence_id}"
                    )
    if len(cases) > limits.max_cases:
        coverage.truncations.append("max_cases")
    order = {"must_review": 0, "should_review": 1, "may_review": 2}
    cases = sorted(cases, key=lambda c: (order[c.review_priority], c.case_id))[: limits.max_cases]
    coverage.gaps = sorted(set(coverage.gaps))
    coverage.truncations = sorted(set(coverage.truncations))
    coverage.returned_cases = len(cases)
    coverage.complete = not (coverage.gaps or coverage.truncations or coverage.unmatched_operations)
    return AnalysisResult(
        analysis_id=content_id(
            "analysis",
            [
                source.model_dump(),
                limits.model_dump(),
                RULE_VERSION,
            ],
        ),
        assertions=assertions,
        cases=cases,
        coverage=coverage,
    )


def _case(source, op, seed, artifact, assertions, paths, identity_resolved):
    evidence = {e.evidence_id: e for e in source.evidence}
    documents = {d.document_id: d for d in source.documents}
    evidence_ids = sorted({eid for path in paths for edge in path for eid in edge.evidence_ids})
    references = (
        "incomplete_graph_merge" not in source.source_gaps
        and bool(evidence_ids)
        and all(
            eid in evidence
            and evidence[eid].document_id in documents
            and bool(documents[evidence[eid].document_id].hash)
            and eid not in source.stale_evidence_ids
            for eid in evidence_ids
        )
    )
    # An edge is grounded only by its own supplied evidence, not another path's quote.
    grounded = any(
        all(
            edge.polarity == "explicit"
            and edge.status == "confirmed"
            and edge.evidence_ids
            and all(
                eid in evidence and eid not in source.stale_evidence_ids
                for eid in edge.evidence_ids
            )
            for edge in path
        )
        for path in paths
    )
    direct = any(len(path) == 1 and path[0].relation_type in DIRECT for path in paths)
    unresolved = list(op.unresolved)
    if not references:
        unresolved.append("missing_or_stale_source_evidence")
    if not identity_resolved:
        unresolved.append("ambiguous_identity")
    if not grounded:
        unresolved.append("unconfirmed_or_inferred_path")
    if not direct:
        unresolved.append("dependency_transformation_not_verified")
    if assertions and not all(
        any(
            len(path) == 1
            and path[0].relation_type in DIRECT
            and path[0].status == "confirmed"
            and path[0].polarity == "explicit"
            and assertion.anchor.evidence_id in path[0].evidence_ids
            for path in paths
        )
        for assertion in assertions
    ):
        unresolved.append("unconfirmed_property_assertion")
    if op.before and op.after and (op.before.unit == "unknown" or op.before.unit != op.after.unit):
        unresolved.append("change_unit_conversion_not_verified")
    if op.conditions or any(a.conditions for a in assertions):
        unresolved.append("conditions_require_review")
    values = {(a.value.value, a.value.unit) for a in assertions}
    if len(values) > 1:
        unresolved.append("contradictory_source_assertions")
    comparable = bool(op.after and assertions) and all(
        a.value.unit != "unknown" and a.value.unit == op.after.unit for a in assertions
    )
    if not comparable:
        unresolved.append("unknown_or_incompatible_units")
    if not assertions:
        unresolved.append("no_labelled_property_evidence")
    verification = Verification(
        references_valid=references,
        identity_resolved=identity_resolved,
        path_grounded=grounded,
        property_supported=bool(assertions),
        units_comparable=comparable,
        unresolved=sorted(set(unresolved)),
    )
    outcome, priority = "unresolved", "should_review"
    reason = "仕様・単位・依存経路の前提を原典で確認してください。"
    actions = ["未解決の前提と原典を確認する"]
    if op.property != "max_length":
        outcome, priority = "unsupported", "may_review"
        reason = "この変更propertyには型付き比較規則がありません。"
    elif not verification.unresolved:
        current = assertions[0].value.value
        desired = op.after.value
        if "test" in artifact.artifact_type.lower():
            outcome = "test_review"
            reason = "変更後の境界値と期待結果を確認してください。"
            actions = [f"{desired}と{desired + 1}の境界値テストを確認する"]
        elif (
            current < desired
            if artifact.artifact_type.lower() in {"table", "column", "dbcolumn"}
            else current != desired
        ):
            outcome, priority = "inconsistency", "must_review"
            reason = f"現行の最大長{current}と変更後の{desired}に制約不整合があります。"
            actions = [f"{artifact.display_name}の最大長{current}を新仕様{desired}と照合する"]
        else:
            outcome, priority = "satisfied", "may_review"
            reason = f"確認した最大長{current}は{desired}を保持可能です。この制約のみの評価です。"
            actions = ["この制約以外の影響と適用条件をレビューする"]
    strength = (
        "strong"
        if references and grounded and assertions and identity_resolved
        else ("medium" if references and assertions else "weak" if references else "none")
    )
    return ImpactCase(
        case_id=content_id("case", [op.operation_id, artifact.artifact_id, seed.entity_id]),
        operation_id=op.operation_id,
        artifact_id=artifact.artifact_id,
        subject_id=seed.entity_id,
        assertion_ids=sorted(a.assertion_id for a in assertions),
        evidence_ids=evidence_ids,
        relation_paths=sorted([e.relation_id for e in p] for p in paths),
        outcome=outcome,
        review_priority=priority,
        evidence_strength=strength,
        reason=reason,
        required_actions=actions,
        verification=verification,
    )
