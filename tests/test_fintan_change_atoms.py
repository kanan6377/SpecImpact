from __future__ import annotations

from pathlib import Path

import pytest

from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.store import LocalStore


@pytest.mark.parametrize(
    ("body", "arrow"),
    [
        ("プロジェクト名の最大長を128文字から256文字へ変更", None),
        ("プロジェクト名 128→256", "→"),
        ("プロジェクト名 128->256", "->"),
        ("プロジェクト名 128=>256", "=>"),
        ("プロジェクト名 128-->256", "-->") ,
    ],
)
def test_japanese_length_change_is_deterministic(
    tmp_path: Path, body: str, arrow: str | None
) -> None:
    change_path = tmp_path / "project_name.md"
    change_path.write_text(body, encoding="utf-8")

    extraction = parse_change_atoms(LocalStore(tmp_path / ".specimpact"), change_path)

    atom = extraction.change_atoms[0]
    assert atom.target_terms == ["プロジェクト名"]
    assert atom.operation == "change_constraint"
    assert atom.property == "length"
    assert atom.before == "128"
    assert atom.after == "256"


@pytest.mark.parametrize("label", ["最大長", "最大桁数", "文字数", "桁数"])
def test_japanese_length_labels_map_to_length(tmp_path: Path, label: str) -> None:
    change_path = tmp_path / "project_name.md"
    change_path.write_text(
        f"プロジェクト名の{label}を128から256へ変更", encoding="utf-8"
    )

    atom = parse_change_atoms(LocalStore(tmp_path / ".specimpact"), change_path).change_atoms[0]

    assert atom.property == "length"
    assert atom.operation == "change_constraint"
    assert atom.before == "128"
    assert atom.after == "256"


def test_utf8_bom_is_stripped_before_parsing(tmp_path: Path) -> None:
    change_path = tmp_path / "project_name.md"
    change_path.write_text(
        chr(0xFEFF) + "プロジェクト名の最大長を128文字から256文字へ変更",
        encoding="utf-8",
    )

    atom = parse_change_atoms(LocalStore(tmp_path / ".specimpact"), change_path).change_atoms[0]

    assert atom.target_terms == ["プロジェクト名"]
    assert atom.operation == "change_constraint"
    assert atom.before == "128"
    assert atom.after == "256"
