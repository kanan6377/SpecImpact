from __future__ import annotations

import re
import unicodedata

from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.models import Document, Entity, Evidence, Relation
from specimpact.semantic.models import (
    ChangeOperation,
    LengthValue,
    Mention,
    SourceAnchor,
    SpecAssertion,
    content_id,
)

LABEL = r"max[_ ]?length|maximum length|最大文字数|最大長|最大桁数|文字数|桁数"
LENGTH = re.compile(
    rf"(?:{LABEL})\s*[:：=は]?\s*(\d+)\s*(文字|バイト|characters?|chars?|bytes?)?",
    re.IGNORECASE,
)
UNIT = re.compile(r"文字|characters?|chars?|バイト|bytes?", re.IGNORECASE)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().replace("_", "").strip()


def mentions(text: str, term: str) -> bool:
    if not term.strip():
        return False
    normalized, target = normalize(text), normalize(term)
    if target.isascii():
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(target)}(?![a-z0-9])", normalized))
    return target in normalized


def unit_for(text: str) -> str:
    units = {m.group().casefold() for m in UNIT.finditer(text)}
    byte = any(u.startswith("byte") or u == "バイト" for u in units)
    char = any(u.startswith("char") or u == "文字" for u in units)
    return "unknown" if byte == char else "bytes" if byte else "characters"


def operation_from_atom(atom: ChangeAtom) -> ChangeOperation:
    unresolved = []
    values = []
    for name in ("before", "after"):
        raw = getattr(atom, name)
        match = re.fullmatch(r"\s*(\d+)\s*(文字|バイト|characters?|chars?|bytes?)?\s*", raw or "")
        if atom.property != "length" or not match:
            values.append(None)
            unresolved.append(f"{name}_not_a_typed_length")
        else:
            explicit_unit = getattr(atom, f"{name}_unit")
            values.append(
                LengthValue(
                    value=int(match[1]),
                    unit=(explicit_unit if explicit_unit != "unknown" else unit_for(raw or "")),
                )
            )
    return ChangeOperation(
        operation_id=atom.atom_id,
        change_id=atom.change_id,
        target_terms=atom.target_terms,
        scope=atom.scope,
        property="max_length" if atom.property == "length" else (atom.property or atom.operation),
        before=values[0],
        after=values[1],
        conditions=atom.conditions,
        unresolved=unresolved,
    )


def anchor_for(evidence: Evidence, documents: dict[str, Document]) -> SourceAnchor:
    doc = documents.get(evidence.document_id)
    location = evidence.source_location
    sheet = re.search(r"\[([^\[\]]+)!([A-Z]+[0-9]+(?::[A-Z]+[0-9]+)?)\]", evidence.quote)
    return SourceAnchor(
        evidence_id=evidence.evidence_id,
        document_id=evidence.document_id,
        source_hash=doc.hash if doc else "",
        quote_hash=content_id("quote", evidence.quote),
        file=location.file,
        line_start=max(1, location.line_start),
        line_end=max(1, location.line_end),
        sheet=sheet[1] if sheet else None,
        cells=sorted(
            set(re.findall(r"\b[A-Z]{1,3}[1-9][0-9]*(?::[A-Z]+[0-9]+)?\b", evidence.quote))
        ),
    )


def extract_assertions(
    entities: list[Entity],
    relations: list[Relation],
    evidence: list[Evidence],
    documents: list[Document],
) -> tuple[list[Mention], list[SpecAssertion]]:
    docs = {d.document_id: d for d in documents}
    by_evidence: dict[str, list[Relation]] = {}
    for relation in relations:
        if relation.status != "rejected":
            for eid in relation.evidence_ids:
                by_evidence.setdefault(eid, []).append(relation)
    found_mentions, assertions = {}, {}
    for ev in evidence:
        anchor = anchor_for(ev, docs)
        rows = _rows(ev.quote)
        for entity in entities:
            names = [entity.entity_id, entity.display_name, entity.canonical_name, *entity.aliases]
            if not any(mentions(ev.quote, n) for n in names):
                continue
            mention = Mention(
                mention_id=content_id("mention", [ev.evidence_id, entity.entity_id]),
                text=entity.display_name,
                entity_id=entity.entity_id,
                scope=entity.scope,
                anchor=anchor,
            )
            found_mentions[mention.mention_id] = mention
            related = [
                r for r in by_evidence.get(ev.evidence_id, []) if r.target_id == entity.entity_id
            ]
            for row, header in rows:
                if not any(mentions(row, n) for n in names):
                    continue
                # Do not attach one row's value to several distinct fields.
                other_fields = [
                    e
                    for e in entities
                    if e.entity_id != entity.entity_id
                    and normalize(e.display_name) != normalize(entity.display_name)
                    and any(mentions(row, n) for n in [e.display_name, e.canonical_name])
                ]
                if other_fields:
                    continue
                value, method = _length(row, header)
                if value is None:
                    continue
                conditions = [row] if re.search(r"\bif\b|場合|条件", row, re.I) else []
                for relation in related:
                    assertion = SpecAssertion(
                        assertion_id=content_id(
                            "assertion",
                            [
                                ev.evidence_id,
                                relation.source_id,
                                entity.entity_id,
                                row,
                            ],
                        ),
                        subject_id=entity.entity_id,
                        artifact_id=relation.source_id,
                        scope=entity.scope,
                        value=value,
                        conditions=conditions,
                        anchor=anchor,
                        extraction_method=method,
                        status=relation.status,
                    )
                    assertions[assertion.assertion_id] = assertion
    return (
        sorted(found_mentions.values(), key=lambda m: m.mention_id),
        sorted(assertions.values(), key=lambda a: a.assertion_id),
    )


def _rows(quote: str) -> list[tuple[str, list[str]]]:
    rows, header = [], []
    for row in re.split(r"\n| / |[;；]", quote):
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) > 1 and any(re.fullmatch(LABEL, c, re.I) for c in cells):
            header = cells
            continue
        rows.append((row, header))
    return rows


def _length(row: str, header: list[str]) -> tuple[LengthValue | None, str]:
    matches = list(LENGTH.finditer(row))
    if len(matches) == 1:
        match = matches[0]
        return LengthValue(value=int(match[1]), unit=unit_for(match.group())), "labelled_text"
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    if header and len(cells) == len(header):
        indexes = [i for i, h in enumerate(header) if re.fullmatch(LABEL, h, re.I)]
        if len(indexes) == 1:
            cell = re.sub(r"\[[A-Z]+[0-9]+\]\s*", "", cells[indexes[0]])
            match = re.fullmatch(r"(\d+)\s*(文字|バイト|characters?|chars?|bytes?)?", cell, re.I)
            if match:
                return LengthValue(value=int(match[1]), unit=unit_for(cell)), "labelled_table"
    return None, "labelled_text"
