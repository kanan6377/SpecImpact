from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


def validate_report(report: dict[str, object]) -> None:
    _validate("report.schema.json", report)


def validate_relation(relation: dict[str, object]) -> None:
    _validate("relation.schema.json", relation)


def validate_evidence(evidence: dict[str, object]) -> None:
    _validate("evidence.schema.json", evidence)


def _validate(schema_name: str, payload: dict[str, object]) -> None:
    schema_dir = _schema_dir()
    schema = json.loads(schema_dir.joinpath(schema_name).read_text(encoding="utf-8"))
    registry = Registry().with_resources(
        (
            schema["$id"],
            Resource.from_contents(schema),
        )
        for path in schema_dir.iterdir()
        if path.name.endswith(".schema.json")
        for schema in [json.loads(path.read_text(encoding="utf-8"))]
    )
    Draft202012Validator(schema, registry=registry).validate(payload)


def _schema_dir():
    source = Path(__file__).parents[1] / "schemas" / "v1"
    if source.is_dir():
        return source
    return files("specimpact").joinpath("resources", "schemas", "v1")
