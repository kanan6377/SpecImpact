from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from specimpact.graphrag import LLMClient
from specimpact.store import LocalStore


class ChangeAtom(BaseModel):
    atom_id: str
    change_id: str
    target_terms: list[str]
    operation: str
    property: str | None = None
    before: str | None = None
    after: str | None = None
    likely_node_types: list[str] = Field(default_factory=list)
    scope: str = ""
    before_unit: Literal["characters", "bytes", "unknown"] = "unknown"
    after_unit: Literal["characters", "bytes", "unknown"] = "unknown"
    conditions: list[str] = Field(default_factory=list)


class ChangeAtomExtraction(BaseModel):
    change_id: str
    change_atoms: list[ChangeAtom]


DEFAULT_NODE_TYPES = [
    "ScreenField",
    "ValidationRule",
    "APIField",
    "DBColumn",
    "TestCase",
    "ExternalIF",
]


def parse_change_atoms(
    store: LocalStore,
    change_path: Path,
    client: LLMClient | None = None,
) -> ChangeAtomExtraction:
    if not change_path.is_file():
        raise ValueError(f"Change request does not exist: {change_path}")
    body = change_path.read_text(encoding="utf-8-sig")
    change_id = f"change.{change_path.stem}"
    if client:
        extraction = client.structured(
            "change_atom_extraction",
            {"change_id": change_id, "change_request": body},
            ChangeAtomExtraction,
        )
    else:
        extraction = ChangeAtomExtraction(
            change_id=change_id,
            change_atoms=_heuristic_atoms(change_id, body),
        )
    store.write("change_atoms", _merge_atoms(store.read("change_atoms", ChangeAtom), extraction))
    return extraction


def show_change(store: LocalStore, change_id: str) -> str:
    atoms = [item for item in store.read("change_atoms", ChangeAtom) if item.change_id == change_id]
    if not atoms:
        raise ValueError(f"Unknown change: {change_id}")
    return json.dumps([item.model_dump() for item in atoms], ensure_ascii=False, indent=2)


def list_changes(store: LocalStore) -> str:
    by_change: dict[str, int] = {}
    for atom in store.read("change_atoms", ChangeAtom):
        by_change[atom.change_id] = by_change.get(atom.change_id, 0) + 1
    rows = [
        {"change_id": change_id, "atoms": count}
        for change_id, count in sorted(by_change.items())
    ]
    return json.dumps(
        rows,
        ensure_ascii=False,
        indent=2,
    )


def _heuristic_atoms(change_id: str, body: str) -> list[ChangeAtom]:
    clauses = [line.strip().lstrip("-* ") for line in re.split(r"[\n。；;]", body)
               if line.strip() and not line.strip().startswith("#")]
    if len(clauses) > 1:
        parsed = [_heuristic_atoms(change_id, clause) for clause in clauses]
        concrete = [atom for group in parsed for atom in group if atom.before or atom.after]
        if concrete:
            return list({atom.atom_id: atom for atom in concrete}.values())
    text = body.replace("\n", " ")
    patterns = [
        (
            r"(?P<target>[一-龥ぁ-んァ-ヶA-Za-z0-9_]+?)の"
            r"(?P<prop>最大長|最大桁数|文字数|桁数)を"
            r"(?P<before>[0-9]+)(?P<bu>文字|桁|バイト)?から"
            r"(?P<after>[0-9]+)(?P<au>文字|桁|バイト)?へ"
        ),
        (
            r"(?P<target>[一-龥ぁ-んァ-ヶA-Za-z0-9_]+?)\s+"
            r"(?P<before>[0-9]+)\s*(?:→|->|=>|-->)\s*(?P<after>[0-9]+)"
        ),
        r"[「\"](?P<target>[^」\"]+)[」\"].*?(?P<prop>上限|下限|桁数|必須|方式|値).*?(?P<before>[0-9A-Za-z一-龥ぁ-んァ-ヶ万円]+)から(?P<after>[0-9A-Za-z一-龥ぁ-んァ-ヶ万円]+)",
        r"(?P<target>[一-龥ぁ-んァ-ヶA-Za-z0-9_]+).*?(?P<prop>上限|下限|桁数|必須|方式|値).*?(?P<before>[0-9A-Za-z一-龥ぁ-んァ-ヶ万円]+)から(?P<after>[0-9A-Za-z一-龥ぁ-んァ-ヶ万円]+)",
        r"(?P<target>[A-Za-z_][A-Za-z0-9_]+).*?(?P<before>[0-9]+).*?(?P<after>[0-9]+)",
    ]
    for pattern_index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if not match:
            continue
        target = match.group("target").strip(" の")
        target_terms = _target_terms(target, text)
        prop = (
            "length"
            if pattern_index == 1
            else _property_for(match.groupdict().get("prop") or "")
        )
        before = _clean_value(match.groupdict().get("before"))
        after = _clean_value(match.groupdict().get("after"))
        return [
            ChangeAtom(
                atom_id=f"atom.{_short_hash(change_id + target + str(before) + str(after))}",
                change_id=change_id,
                target_terms=target_terms,
                operation=(
                    "change_constraint"
                    if prop in {"max_value", "min_value", "length"}
                    else "change_spec"
                ),
                property=prop,
                before=before,
                after=after,
                likely_node_types=DEFAULT_NODE_TYPES,
                before_unit={"文字": "characters", "バイト": "bytes"}.get(
                    match.groupdict().get("bu"), "unknown"
                ),
                after_unit={"文字": "characters", "バイト": "bytes"}.get(
                    match.groupdict().get("au"), "unknown"
                ),
            )
        ]
    fallback = next(
        (line.lstrip("# ").strip() for line in body.splitlines() if line.strip()),
        body[:40],
    )
    return [
        ChangeAtom(
            atom_id=f"atom.{_short_hash(change_id + fallback)}",
            change_id=change_id,
            target_terms=_target_terms(fallback, text),
            operation="change_spec",
            likely_node_types=DEFAULT_NODE_TYPES,
        )
    ]


def _merge_atoms(current: list[ChangeAtom], extraction: ChangeAtomExtraction) -> list[ChangeAtom]:
    kept = [item for item in current if item.change_id != extraction.change_id]
    return kept + extraction.change_atoms


def _property_for(label: str) -> str | None:
    if label in {"最大長", "最大桁数", "文字数", "桁数"}:
        return "length"
    if "上限" in label:
        return "max_value"
    if "下限" in label:
        return "min_value"
    if "桁" in label:
        return "length"
    if "必須" in label:
        return "required"
    if "方式" in label:
        return "method"
    return None


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    return value.strip(" をに、。")


def _target_terms(target: str, text: str) -> list[str]:
    terms = [target]
    terms.extend(
        match
        for match in re.findall(r"\b[A-Za-z][A-Za-z0-9_]*Limit[A-Za-z0-9_]*\b", text)
        if match not in terms
    )
    terms.extend(
        match
        for match in re.findall(r"\b[A-Z][A-Z0-9_]*LIMIT[A-Z0-9_]*\b", text)
        if match not in terms
    )
    if "限度" in target or "限度" in text:
        for alias in ("requestedCreditLimit", "REQUESTED_CREDIT_LIMIT", "LIMIT_AMT"):
            if alias not in terms:
                terms.append(alias)
    return terms


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
