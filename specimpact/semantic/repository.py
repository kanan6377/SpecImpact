from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field

from specimpact.dirty_excel.models import DirtySheet
from specimpact.extraction import AliasCatalog
from specimpact.impact_management.change_atoms import ChangeAtom
from specimpact.locking import ProjectWriteLock
from specimpact.models import Artifact, Document, Entity, Evidence, Relation, utc_now
from specimpact.semantic.extraction import operation_from_atom
from specimpact.semantic.kernel import (
    AnalysisInput,
    AnalysisLimits,
    AnalysisResult,
    analyze,
)
from specimpact.semantic.models import Contract, content_id
from specimpact.source_freshness import StaleRecord
from specimpact.store import LocalStore


class DecisionEvent(Contract):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    analysis_id: str
    case_id: str
    actor: str = Field(min_length=1)
    status: Literal[
        "accepted", "rejected", "needs_investigation", "implemented", "tested", "closed"
    ]
    reason: str = Field(min_length=1)
    created_at: str = Field(default_factory=utc_now)


class AnalysisRepository:
    """Immutable normalized-source snapshots; SQLite owns kernel runs and decision events."""

    def __init__(self, root: Path):
        self.path = root / "analysis.sqlite3"

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS runs (
                    analysis_id TEXT PRIMARY KEY,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    limits_json TEXT NOT NULL, result_json TEXT NOT NULL,
                    result_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS report_links (
                    report_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL REFERENCES runs(analysis_id));
                CREATE TABLE IF NOT EXISTS decisions (
                    event_id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL REFERENCES runs(analysis_id),
                    payload TEXT NOT NULL);
            """)
            with connection:
                yield connection
        finally:
            connection.close()

    def save(
        self,
        source: AnalysisInput,
        *,
        report_id: str | None = None,
        limits: AnalysisLimits | None = None,
    ) -> AnalysisResult:
        limits = limits or AnalysisLimits()
        result = analyze(source, limits)
        snapshot_id = content_id("snapshot", source.model_dump())
        with self.connection() as db:
            db.execute(
                "INSERT OR IGNORE INTO snapshots VALUES (?, ?)",
                (snapshot_id, source.model_dump_json()),
            )
            self._insert_result(db, snapshot_id, limits, result)
            if report_id:
                existing = db.execute(
                    "SELECT analysis_id FROM report_links WHERE report_id=?", (report_id,)
                ).fetchone()
                if existing and existing[0] != result.analysis_id:
                    raise ValueError("Report ID already references another immutable analysis")
                db.execute(
                    "INSERT OR IGNORE INTO report_links VALUES (?, ?)",
                    (report_id, result.analysis_id),
                )
        return result

    @staticmethod
    def _insert_result(db, snapshot_id, limits, result):
        db.execute(
            "INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?, ?)",
            (
                result.analysis_id,
                snapshot_id,
                limits.model_dump_json(),
                result.model_dump_json(),
                content_id("result", result.model_dump()),
            ),
        )

    def load(self, identifier: str) -> tuple[AnalysisInput, AnalysisLimits, AnalysisResult]:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT s.snapshot_id, s.payload, r.limits_json, r.result_json, r.result_hash
                FROM runs r JOIN snapshots s ON r.snapshot_id=s.snapshot_id
                WHERE r.analysis_id=? OR r.analysis_id=(
                    SELECT analysis_id FROM report_links WHERE report_id=?)
            """,
                (identifier, identifier),
            ).fetchone()
        if row is None:
            raise ValueError(f"Unknown analysis or report: {identifier}")
        source = AnalysisInput.model_validate_json(row[1])
        result = AnalysisResult.model_validate_json(row[3])
        if content_id("snapshot", source.model_dump()) != row[0]:
            raise ValueError("Analysis snapshot integrity check failed")
        if content_id("result", result.model_dump()) != row[4]:
            raise ValueError("Analysis result integrity check failed")
        return source, AnalysisLimits.model_validate_json(row[2]), result

    def replay(self, identifier: str) -> AnalysisResult:
        source, limits, expected = self.load(identifier)
        actual = analyze(source, limits)
        if actual != expected:
            raise ValueError("Replay differs: stored rules or extraction version is incompatible")
        return actual

    def export(self, identifier: str) -> dict:
        source, limits, result = self.load(identifier)
        return {
            "schema_version": "2",
            "source": source.model_dump(),
            "limits": limits.model_dump(),
            "result": result.model_dump(),
        }

    def import_snapshot(self, payload: dict) -> AnalysisResult:
        if payload.get("schema_version") != "2":
            raise ValueError("Unsupported snapshot schema")
        source = AnalysisInput.model_validate(payload["source"])
        limits = AnalysisLimits.model_validate(payload["limits"])
        expected = AnalysisResult.model_validate(payload["result"])
        if analyze(source, limits) != expected:
            raise ValueError("Imported snapshot failed deterministic replay")
        return self.save(source, limits=limits)

    def decide(self, event: DecisionEvent) -> None:
        _, _, result = self.load(event.analysis_id)
        if event.case_id not in {c.case_id for c in result.cases}:
            raise ValueError("Decision case does not belong to this analysis")
        with self.connection() as db:
            existing = db.execute(
                "SELECT payload FROM decisions WHERE event_id=?", (event.event_id,)
            ).fetchone()
            if existing and DecisionEvent.model_validate_json(existing[0]) != event:
                raise ValueError("Decision event is immutable")
            db.execute(
                "INSERT OR IGNORE INTO decisions VALUES (?, ?, ?)",
                (event.event_id, event.analysis_id, event.model_dump_json()),
            )

    def decisions(self, analysis_id: str) -> list[DecisionEvent]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT payload FROM decisions WHERE analysis_id=? ORDER BY rowid", (analysis_id,)
            ).fetchall()
        return [DecisionEvent.model_validate_json(row[0]) for row in rows]


def capture(store: LocalStore, atoms: list[ChangeAtom]) -> AnalysisInput:
    """Copy legacy ingest data under its process lock; never mutate the source workspace."""
    with ProjectWriteLock(store.root):
        aliases = AliasCatalog.load(store.root / "aliases.yml")
        entities = store.read("entities", Entity)
        for entity in entities:
            entity.aliases = sorted(
                set(entity.aliases) | set(aliases.aliases_for(entity.entity_id))
            )
        documents = [
            d.model_copy(update={"loaded_at": ""}) for d in store.read("documents", Document)
        ]
        gaps = []
        merge_state = store.root / "graph_merge_state.json"
        if merge_state.exists() and json.loads(merge_state.read_text(encoding="utf-8")).get(
            "status"
        ) != "ready":
            gaps.append("incomplete_graph_merge")
        for sheet in store.read("dirty_sheets", DirtySheet):
            if sheet.sheet_type == "unknown":
                gaps.append(f"unknown_sheet:{sheet.sheet_id}")
            if sheet.image_count or sheet.chart_count or sheet.unsupported_drawings:
                gaps.append(f"unsupported_drawing:{sheet.sheet_id}")
        return AnalysisInput(
            documents=sorted(documents, key=lambda d: d.document_id),
            entities=sorted(entities, key=lambda e: e.entity_id),
            artifacts=sorted(store.read("artifacts", Artifact), key=lambda a: a.artifact_id),
            relations=sorted(store.read("relations", Relation), key=lambda r: r.relation_id),
            evidence=sorted(store.read("evidence", Evidence), key=lambda e: e.evidence_id),
            operations=sorted(
                [operation_from_atom(a) for a in atoms], key=lambda o: o.operation_id
            ),
            stale_evidence_ids=sorted(
                {
                    s.target_id
                    for s in store.read("stale_records", StaleRecord)
                    if s.target_type == "evidence" and not s.resolved_at
                }
            ),
            source_gaps=sorted(gaps),
        )


def workspace_fingerprint(store: LocalStore, atoms: list[ChangeAtom]) -> str:
    return content_id("workspace", capture(store, atoms).model_dump())


def read_export(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
