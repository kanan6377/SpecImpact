from __future__ import annotations

from collections import deque

from specimpact.extraction import AliasCatalog
from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.models import Entity, Evidence, Relation
from specimpact.store import LocalStore


class RetrievedPath:
    def __init__(self, node_id: str, relations: list[Relation], evidence_ids: list[str]) -> None:
        self.node_id = node_id
        self.relations = relations
        self.evidence_ids = evidence_ids


EXPAND_RELATIONS = {
    "DEFINES",
    "DISPLAYS",
    "VALIDATES",
    "REQUEST_FIELD",
    "RESPONSE_FIELD",
    "READS",
    "WRITES",
    "SENDS",
    "RECEIVES",
    "CALLS",
    "COVERS",
    "MENTIONS",
    "contains",
    "displays",
    "accepts_input",
    "validates",
    "calls",
    "reads",
    "writes",
    "maps_to",
    "sends",
    "receives",
    "tested_by",
    "depends_on",
    "may_affect",
}


def retrieve_impacts(store: LocalStore, atoms: list[ChangeAtom]) -> list[RetrievedPath]:
    entities = store.read("entities", Entity)
    relations = store.read("relations", Relation)
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    aliases = AliasCatalog.load(store.root / "aliases.yml")
    seeds = _seed_entities(entities, atoms, aliases)
    if not seeds:
        seeds = _seed_from_evidence(relations, evidence, atoms)
    paths: dict[str, RetrievedPath] = {}
    incoming: dict[str, list[Relation]] = {}
    for relation in relations:
        if relation.relation_type in EXPAND_RELATIONS and relation.status != "rejected":
            incoming.setdefault(relation.target_id, []).append(relation)
    queue = deque((seed, [], []) for seed in seeds)
    visited = set(seeds)
    while queue:
        node_id, path, evidence_ids = queue.popleft()
        for relation in incoming.get(node_id, []):
            next_path = [*path, relation]
            next_evidence = sorted({*evidence_ids, *relation.evidence_ids})
            current = paths.get(relation.source_id)
            if current is None or len(next_path) < len(current.relations):
                paths[relation.source_id] = RetrievedPath(
                    relation.source_id,
                    next_path,
                    next_evidence,
                )
            elif len(next_path) == len(current.relations):
                # A sheet can mention the same field in several evidence-addressed regions.
                # Keep one shortest graph path, but retain all equal-distance supporting evidence
                # so boundary values are not lost merely because another region was visited first.
                current.evidence_ids = sorted({*current.evidence_ids, *next_evidence})
            if (
                len(next_path) < _max_depth(relation.relation_type)
                and relation.source_id not in visited
            ):
                visited.add(relation.source_id)
                queue.append((relation.source_id, next_path, next_evidence))
    return list(paths.values())


def _seed_entities(
    entities: list[Entity],
    atoms: list[ChangeAtom],
    aliases: AliasCatalog,
) -> set[str]:
    terms = {term for atom in atoms for term in atom.target_terms if term}
    seeds = set()
    for entity in entities:
        names = {
            entity.display_name,
            entity.canonical_name,
            *entity.aliases,
            *aliases.aliases_for(entity.entity_id),
        }
        if any(_matches(term, name) for term in terms for name in names):
            seeds.add(entity.entity_id)
    return seeds


def _seed_from_evidence(
    relations: list[Relation],
    evidence: dict[str, Evidence],
    atoms: list[ChangeAtom],
) -> set[str]:
    terms = {term for atom in atoms for term in [*atom.target_terms, atom.before or ""] if term}
    seeds = set()
    for relation in relations:
        for evidence_id in relation.evidence_ids:
            quote = evidence.get(evidence_id).quote if evidence_id in evidence else ""
            if any(term in quote for term in terms):
                seeds.add(relation.target_id)
    return seeds


def _matches(term: str, name: str) -> bool:
    if not term or not name:
        return False
    if term in name or name in term:
        return True
    folded = name.casefold().replace("_", "")
    folded_term = term.casefold().replace("_", "")
    return folded_term in folded or folded in folded_term


def _max_depth(relation_type: str) -> int:
    if relation_type == "MENTIONS":
        return 1
    if relation_type in {"DEFINES", "DISPLAYS", "VALIDATES", "REQUEST_FIELD", "SENDS", "COVERS"}:
        return 3
    return 2
