from __future__ import annotations

from specimpact.models import Evidence, Relation
from specimpact.store import LocalStore


def classify_impact(
    store: LocalStore,
    relation_path: list[Relation],
    evidence_ids: list[str],
    target_terms: list[str],
    before: str | None,
    *,
    change_property: str | None = None,
    artifact_type: str | None = None,
) -> tuple[str, str]:
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    selected = [evidence[item] for item in evidence_ids if item in evidence]
    if not relation_path or not selected:
        return "hidden", "No graph path with persisted evidence was found."
    text = "\n".join(item.quote for item in selected)
    direct_term = any(term and term in text for term in target_terms)
    direct_before = bool(before and before in text)
    has_explicit_path = any(relation.polarity == "explicit" for relation in relation_path)
    all_inferred = all(relation.polarity == "inferred" for relation in relation_path)
    compatible = _property_compatible(change_property, artifact_type)
    if has_explicit_path and (direct_term or direct_before):
        if not compatible:
            return (
                "should_review",
                "Evidence exists, but change property and artifact type are weakly related.",
            )
        if before and not direct_before and _requires_before_evidence(artifact_type):
            return "should_review", "Target evidence exists, but the before value was not found."
        return "must_review", "Direct evidence and graph path were found."
    if all_inferred and not direct_term:
        return "may_review", "Only inferred relations connected this candidate."
    if has_explicit_path:
        return "should_review", "Graph path exists, but direct term evidence is weak."
    return "may_review", "Semantic or inferred relation exists with weak grounding."


def _property_compatible(change_property: str | None, artifact_type: str | None) -> bool:
    if not change_property or not artifact_type:
        return True
    artifact = artifact_type.lower()
    prop = change_property.lower()
    if prop in {"max_value", "min_value", "length", "required"}:
        return any(
            token in artifact
            for token in (
                "field",
                "validation",
                "column",
                "table",
                "api",
                "screen",
                "test",
                "external",
            )
        )
    return True


def _requires_before_evidence(artifact_type: str | None) -> bool:
    if not artifact_type:
        return False
    artifact = artifact_type.lower()
    return any(token in artifact for token in ("validation", "test"))
