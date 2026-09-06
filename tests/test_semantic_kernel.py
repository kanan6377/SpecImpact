import pytest
from test_semantic_models import graph

from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.models import Artifact, Entity
from specimpact.semantic.extraction import operation_from_atom
from specimpact.semantic.kernel import AnalysisInput, AnalysisLimits, analyze


def source(quote="name maxLength: 128 characters", artifact_type="API"):
    entities, relations, evidence, documents = graph(quote)
    atom = ChangeAtom(
        atom_id="op",
        change_id="change",
        target_terms=["name"],
        operation="change_constraint",
        property="length",
        before="128",
        after="256",
        before_unit="characters",
        after_unit="characters",
        scope="system-a",
    )
    return AnalysisInput(
        entities=entities,
        relations=relations,
        evidence=evidence,
        documents=documents,
        artifacts=[Artifact(artifact_id="api", artifact_type=artifact_type, display_name="API")],
        operations=[operation_from_atom(atom)],
    )


@pytest.mark.parametrize(
    ("quote", "kind", "outcome"),
    [
        ("name maxLength: 128 characters", "API", "inconsistency"),
        ("name maxLength: 512 characters", "Table", "satisfied"),
        ("name maxLength: 512 characters", "API", "inconsistency"),
        ("name maxLength: 128 bytes", "ExternalIF", "unresolved"),
        ("name maxLength: 128", "API", "unresolved"),
        ("name maxLength: 128 characters if enabled", "API", "unresolved"),
        ("name 128 is an example", "API", "unresolved"),
        ("name maxLength: 128 characters", "TestCase", "unresolved"),
    ],
)
def test_typed_rule_matrix(quote, kind, outcome):
    data = source(quote, kind)
    if kind == "TestCase":
        data.relations[0].relation_type = "COVERS"
    result = analyze(data)
    assert result.cases[0].outcome == outcome
    assert result == type(result).model_validate_json(result.model_dump_json())
    assert data == AnalysisInput.model_validate_json(data.model_dump_json())
    for value in [result.coverage, result.cases[0], result.cases[0].verification, AnalysisLimits()]:
        assert value == type(value).model_validate_json(value.model_dump_json())


def test_evidence_strength_does_not_derive_from_priority():
    case = analyze(source("name maxLength: 512 characters", "Table")).cases[0]
    assert case.evidence_strength == "strong"
    assert case.review_priority == "may_review"


def test_stale_and_missing_sources_never_get_strong_results():
    data = source()
    data.stale_evidence_ids = ["ev"]
    assert analyze(data).cases[0].outcome == "unresolved"
    data.stale_evidence_ids = []
    data.documents = []
    assert analyze(data).cases[0].evidence_strength == "none"


def test_scoped_identity_and_ambiguous_identity():
    data = source()
    data.entities.append(
        Entity(
            entity_id="other-name",
            entity_type="BusinessField",
            display_name="name",
            canonical_name="name",
            scope="system-b",
        )
    )
    data.relations.append(
        data.relations[0].model_copy(
            update={
                "relation_id": "other-rel",
                "target_id": "other-name",
            }
        )
    )
    assert len(analyze(data).cases) == 1
    data.operations[0].scope = ""
    cases = analyze(data).cases
    assert len(cases) == 2
    assert all("ambiguous_identity" in c.verification.unresolved for c in cases)


def test_multiple_operations_and_conflicts():
    data = source()
    second = data.operations[0].model_copy(deep=True)
    second.operation_id = "op2"
    second.after.value = 512
    data.operations.append(second)
    assert {c.operation_id for c in analyze(data).cases} == {"op", "op2"}
    assert all(c.outcome == "unresolved" for c in analyze(data).cases)
    second.operation_id = "op"
    with pytest.raises(ValueError, match="Duplicate"):
        analyze(data)


def test_coverage_truncation_rejections_and_disconnected_mentions():
    data = source()
    data.relations[0].status = "rejected"
    result = analyze(data)
    assert result.cases == []
    assert result.coverage.excluded_relations == ["rel"]
    assert "disconnected_mention:op:ev" in result.coverage.gaps
    data = source()
    data.source_gaps = ["unsupported_drawing:sheet-a"]
    data.artifacts.append(Artifact(artifact_id="screen", artifact_type="Screen", display_name="UI"))
    data.relations.append(
        data.relations[0].model_copy(
            update={
                "relation_id": "rel2",
                "source_id": "screen",
            }
        )
    )
    result = analyze(data, AnalysisLimits(max_cases=1))
    assert not result.coverage.complete
    assert result.coverage.truncations == ["max_cases"]
    assert len(result.cases) == 1


def test_unmapped_original_match_is_reported():
    data = source()
    data.entities = []
    result = analyze(data)
    assert "unmapped_source_match:op:ev" in result.coverage.gaps
    assert result.coverage.unmatched_operations == ["op"]


def test_multiple_paths_and_contradictory_specifications_survive():
    data = source()
    data.evidence.append(
        data.evidence[0].model_copy(
            update={
                "evidence_id": "ev2",
                "quote": "name maxLength: 64 characters",
            }
        )
    )
    data.relations.append(
        data.relations[0].model_copy(
            update={
                "relation_id": "rel2",
                "evidence_ids": ["ev2"],
            }
        )
    )
    case = analyze(data).cases[0]
    assert len(case.relation_paths) == 2
    assert len(case.assertion_ids) == 2
    assert "contradictory_source_assertions" in case.verification.unresolved


def test_confirmed_neighbor_does_not_validate_an_unconfirmed_property():
    data = source()
    data.relations[0].status = "unconfirmed"
    data.evidence.append(
        data.evidence[0].model_copy(
            update={
                "evidence_id": "mention-only",
                "quote": "name is mentioned here",
            }
        )
    )
    data.relations.append(
        data.relations[0].model_copy(
            update={
                "relation_id": "mention-rel",
                "relation_type": "MENTIONS",
                "status": "confirmed",
                "evidence_ids": ["mention-only"],
            }
        )
    )
    result = analyze(data).cases[0]
    assert result.outcome == "unresolved"
    assert "unconfirmed_property_assertion" in result.verification.unresolved


def test_change_unit_conversion_requires_review():
    data = source()
    data.operations[0].before.unit = "bytes"
    result = analyze(data).cases[0]
    assert result.outcome == "unresolved"
    assert "change_unit_conversion_not_verified" in result.verification.unresolved
