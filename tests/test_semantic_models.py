from pathlib import Path

import pytest
from pydantic import ValidationError

from specimpact.impact_management.change_atoms import ChangeAtom, parse_change_atoms
from specimpact.models import Document, Entity, Evidence, Relation, SourceLocation
from specimpact.semantic.extraction import extract_assertions, operation_from_atom
from specimpact.semantic.models import (
    ChangeOperation,
    IdentityAssertion,
    LengthValue,
    Mention,
    SourceAnchor,
    SpecAssertion,
)
from specimpact.store import LocalStore


def graph(quote="name maxLength: 128 characters", scope="system-a"):
    document = Document(document_id="doc", path="design.md", title="Design", hash="source-v1")
    entity = Entity(
        entity_id="name",
        entity_type="BusinessField",
        display_name="name",
        canonical_name="name",
        scope=scope,
        source_document_ids=["doc"],
    )
    evidence = Evidence(
        evidence_id="ev",
        document_id="doc",
        section_id="sec",
        chunk_id="chunk",
        quote=quote,
        evidence_type="text",
        supports=[],
        source_location=SourceLocation(file="design.md", line_start=1, line_end=1),
    )
    relation = Relation(
        relation_id="rel",
        relation_type="DEFINES",
        source_id="api",
        target_id="name",
        evidence_ids=["ev"],
        status="confirmed",
    )
    return [entity], [relation], [evidence], [document]


def test_all_contracts_round_trip():
    mentions, assertions = extract_assertions(*graph())
    anchor = assertions[0].anchor
    operation = operation_from_atom(
        ChangeAtom(
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
    )
    identity = IdentityAssertion(
        left_id="a", right_id="b", scope="system-a", relation="same", evidence_ids=["ev"]
    )
    models = [anchor, mentions[0], assertions[0], operation, identity, operation.after]
    assert {type(m) for m in models} == {
        SourceAnchor,
        Mention,
        SpecAssertion,
        ChangeOperation,
        IdentityAssertion,
        LengthValue,
    }
    for model in models:
        assert type(model).model_validate_json(model.model_dump_json()) == model
    assert anchor.source_hash == "source-v1"
    assert assertions[0].value == LengthValue(value=128, unit="characters")


@pytest.mark.parametrize("value", [-1, True, "128", 1.5])
def test_lengths_reject_ambiguous_types(value):
    with pytest.raises(ValidationError):
        LengthValue(value=value)


@pytest.mark.parametrize(
    "quote",
    [
        "name appears on page 128",
        "name; unrelated maxLength: 128 characters",
        "surname maxLength: 128 characters",
        "name maxLength: 12 maxLength: 128",
    ],
)
def test_unrelated_numbers_are_not_specifications(quote):
    assert extract_assertions(*graph(quote))[1] == []


def test_table_and_conditions_are_preserved():
    _, assertions = extract_assertions(
        *graph("| field | maxLength |\n| --- | --- |\n| name | 128 bytes |")
    )
    assert assertions[0].value.unit == "bytes"
    _, conditional = extract_assertions(*graph("name maxLength: 128 characters if active"))
    assert conditional[0].conditions


def test_multiple_changes_and_units_round_trip(tmp_path: Path):
    path = tmp_path / "change.md"
    path.write_text(
        "# 変更\nプロジェクト名の最大長を128文字から256文字へ変更。\n"
        "説明の最大長を32バイトから64バイトへ変更",
        encoding="utf-8",
    )
    parsed = parse_change_atoms(LocalStore(tmp_path / ".specimpact"), path)
    assert len(parsed.change_atoms) == 2
    operations = [operation_from_atom(a) for a in parsed.change_atoms]
    assert [o.target_terms for o in operations] == [["プロジェクト名"], ["説明"]]
    assert [o.after.unit for o in operations] == ["characters", "bytes"]
    assert operations[0].operation_id != operations[1].operation_id
    for atom in parsed.change_atoms:
        assert ChangeAtom.model_validate_json(atom.model_dump_json()) == atom
