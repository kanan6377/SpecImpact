from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from specimpact.application.approval import ApprovalManager
from specimpact.application.contracts import (
    ChangeSessionView,
    HostContext,
    PreparedContext,
    Project,
    utc_now,
)
from specimpact.application.mutations import MutationCoordinator
from specimpact.application.security import ProjectWriteLock
from specimpact.dirty_excel.models import DirtyCell, DirtyRegion
from specimpact.graphrag import redact_payload
from specimpact.impact_management.change_atoms import ChangeAtom, ChangeAtomExtraction
from specimpact.impact_management.decision_store import ImpactDecision
from specimpact.impact_management.impact_retrieval import retrieve_impacts
from specimpact.impact_management.report_store import persist_analysis_report
from specimpact.llm_graph.prompts import DIRTY_EXCEL_FEW_SHOTS, prompt_for_region_type
from specimpact.llm_graph.schemas import GraphProposal, RegionExtractionResult
from specimpact.llm_graph.verifier import classify_impact, grounding_strength
from specimpact.models import Artifact, ChangeRequest, Evidence, Impact, Relation
from specimpact.semantic.repository import workspace_fingerprint
from specimpact.store import LocalStore

PRIORITY_ORDER = {"must_review": 0, "should_review": 1, "may_review": 2, "hidden": 3}


class HostImpactHypothesis(BaseModel):
    candidate_node_id: str
    atom_id: str | None = None
    impact_type: str
    required_actions: list[str] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)
    uncertainty: Literal["low", "medium", "high", "unknown"] = "unknown"
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    review_priority_suggestion: Literal[
        "must_review", "should_review", "may_review", "hidden"
    ] | None = None


class HostImpactSubmission(BaseModel):
    change_id: str
    hypotheses: list[HostImpactHypothesis]


class HostWorkflow:
    def __init__(self, project: Project, host_context: HostContext) -> None:
        if host_context.project_id != project.project_id:
            raise ValueError("Host context belongs to another project")
        self.project = project
        self.host = host_context
        self.store = LocalStore(Path(project.path) / ".specimpact")
        self.approvals = ApprovalManager(project)
        self.context_path = self.store.root / "prepared_contexts.jsonl"
        self.session_path = self.store.root / "change_sessions.jsonl"
        self.warning_path = self.store.root / "host_warnings.jsonl"

    def prepare_change(self, change_request: str) -> PreparedContext:
        self._require_initialized()
        body = change_request.strip()
        if not body:
            raise ValueError("Change request text is required")
        change_id = f"change.host.{_short_hash(body)}"
        title = _title(body)
        change_path = self.store.root / "host_changes" / f"{change_id}.md"
        self.store.write_text(change_path, body + ("" if body.endswith("\n") else "\n"))
        payload = {
            "change_id": change_id,
            "change_request": body,
            "output_schema": ChangeAtomExtraction.model_json_schema(),
        }
        return self._prepare(
            purpose="change-atom-extraction",
            schema_name=ChangeAtomExtraction.__name__,
            instructions=(
                "Extract atomic design changes. Preserve target terms, operation, property, "
                "before, after, and likely node types. Do not invent design Evidence."
            ),
            payload=payload,
            evidence_ids=[],
            metadata={
                "change_id": change_id,
                "title": title,
                "change_path": str(change_path),
            },
        )

    def prepare_impact_context(
        self, change_id: str, *, offset: int = 0, limit: int = 100,
    ) -> PreparedContext:
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("offset must be non-negative and limit must be between 1 and 100")
        with ProjectWriteLock(self.store.root):
            return self._prepare_impact_context(change_id, offset, limit)

    def _prepare_impact_context(self, change_id: str, offset: int, limit: int) -> PreparedContext:
        self._require_initialized()
        atoms = [
            item
            for item in self.store.read("change_atoms", ChangeAtom)
            if item.change_id == change_id
        ]
        if not atoms:
            raise KeyError(f"Unknown change: {change_id}")
        artifacts = {item.artifact_id: item for item in self.store.read("artifacts", Artifact)}
        evidence = {item.evidence_id: item for item in self.store.read("evidence", Evidence)}
        candidates = []
        for path in sorted(retrieve_impacts(self.store, atoms),
                           key=lambda p: (p.atom_id or "", p.node_id)):
            artifact = artifacts.get(path.node_id)
            if not artifact:
                continue
            atom = next(a for a in atoms if a.atom_id == path.atom_id)
            candidates.append(
                {
                    "candidate_node_id": artifact.artifact_id,
                    "artifact": artifact.model_dump(),
                    "atom_id": atom.atom_id,
                    "relation_ids": [item.relation_id for item in path.relations],
                    "relations": [item.model_dump() for item in path.relations],
                    "evidence_ids": path.evidence_ids,
                    "evidence": [
                        {
                            "evidence_id": evidence_id,
                            "quote": evidence[evidence_id].quote,
                            "source_location": evidence[evidence_id].source_location.model_dump(),
                        }
                        for evidence_id in path.evidence_ids
                        if evidence_id in evidence
                    ],
                }
            )
        total = len(candidates)
        candidates = candidates[offset:offset + limit]
        payload = {
            "change_id": change_id,
            "change_atoms": [item.model_dump() for item in atoms],
            "candidates": candidates,
            "candidate_page": {"offset": offset, "limit": limit, "total": total,
                               "next_offset": offset + limit if offset + limit < total else None,
                               "partial": offset > 0 or offset + limit < total},
            "output_schema": HostImpactSubmission.model_json_schema(),
        }
        session = self._session_record(change_id)
        request_path = Path(session.get("change_path", ""))
        request_hash = _json_hash(
            request_path.read_text(encoding="utf-8") if request_path.is_file() else ""
        )
        return self._prepare(
            purpose="impact-hypothesis",
            schema_name=HostImpactSubmission.__name__,
            instructions=(
                "Act as an evidence-bound impact analyst. Return concrete impact_type, Japanese "
                "required_actions, warnings, uncertainty, and Evidence IDs for each candidate. "
                "Never elevate priority beyond the supplied Evidence and graph path."
            ),
            payload=payload,
            evidence_ids=sorted(
                {
                    evidence_id
                    for candidate in candidates
                    for evidence_id in candidate["evidence_ids"]
                }
            ),
            metadata={
                "change_id": change_id,
                "title": session.get("title", change_id),
                "change_path": session.get("change_path", ""),
                "workspace_fingerprint": workspace_fingerprint(self.store, atoms),
                "change_request_hash": request_hash,
            },
        )

    def prepare_graph_context(self, region_id: str) -> PreparedContext:
        self._require_initialized()
        region = next(
            (
                item
                for item in self.store.read("dirty_regions", DirtyRegion)
                if item.region_id == region_id
            ),
            None,
        )
        if not region:
            raise KeyError(f"Unknown Dirty Excel region: {region_id}")
        cells = [
            item
            for item in self.store.read("dirty_cells", DirtyCell)
            if item.sheet_id == region.sheet_id
            and region.start_row <= item.row <= region.end_row
            and region.start_column <= item.column <= region.end_column
        ]
        instruction = prompt_for_region_type(region.region_type)
        payload = {
            "region_id": region.region_id,
            "sheet": region.sheet_name,
            "range": region.range,
            "region_type_hint": region.region_type,
            "instruction": instruction,
            "few_shots": DIRTY_EXCEL_FEW_SHOTS,
            "cells_markdown": region.rendered_text,
            "cells": [
                {
                    "cell": item.cell,
                    "value": item.value,
                    "evidence_id": item.evidence_id,
                }
                for item in cells
            ],
            "allowed_evidence_ids": region.evidence_ids,
            "output_schema": RegionExtractionResult.model_json_schema(),
        }
        return self._prepare(
            purpose="dirty-excel-region-extraction",
            schema_name=RegionExtractionResult.__name__,
            instructions=instruction,
            payload=payload,
            evidence_ids=region.evidence_ids,
            metadata={
                "region_id": region.region_id,
                "title": f"{region.sheet_name}!{region.range}",
                "change_id": "",
                "change_path": "",
            },
        )

    def authorize_context(self, context_id: str, grant_token: str) -> PreparedContext:
        record = self._context_record(context_id)
        context = PreparedContext.model_validate(record["context"])
        preview = context.transmission_preview
        if not preview or not preview.required:
            return context
        self.approvals.consume(
            grant_token,
            purpose=context.purpose,
            source_hash=context.source_hash,
        )
        return context

    def submit_change_atoms(
        self,
        context_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> ChangeSessionView:
        record = self._context_record(context_id)
        context = PreparedContext.model_validate(record["context"])
        self._require_purpose(context, "change-atom-extraction")
        try:
            submission = ChangeAtomExtraction.model_validate(payload)
        except ValidationError as error:
            self._log_schema_violation(context, error)
            raise ValueError("Host Change Atom output did not match the required schema") from error
        expected_change_id = record["change_id"]
        if submission.change_id != expected_change_id:
            self._log_warning(context, "change_id_mismatch")
            raise ValueError("Host Change Atom output used an unexpected change_id")
        if not submission.change_atoms or any(
            item.change_id != expected_change_id or not item.target_terms
            for item in submission.change_atoms
        ):
            self._log_warning(context, "invalid_change_atoms")
            raise ValueError("Host Change Atom output must contain grounded target terms")
        change_body = Path(record["change_path"]).read_text(encoding="utf-8")
        for atom in submission.change_atoms:
            for label, value in (("before", atom.before), ("after", atom.after)):
                if value and value not in change_body:
                    self._log_warning(context, f"{label}_value_mismatch")
                    raise ValueError(
                        f"Host Change Atom {label} value was not found in the change request"
                    )

        def operation() -> dict[str, Any]:
            current = [
                item
                for item in self.store.read("change_atoms", ChangeAtom)
                if item.change_id != expected_change_id
            ]
            self.store.write("change_atoms", [*current, *submission.change_atoms])
            self._upsert_session(
                change_id=expected_change_id,
                title=record["title"],
                change_path=record["change_path"],
                status="atoms_ready",
                atom_ids=[item.atom_id for item in submission.change_atoms],
            )
            self._append_audit(context, payload, submission.change_atoms)
            return self.get_session(expected_change_id).model_dump()

        result = MutationCoordinator(self.store).run(
            idempotency_key=idempotency_key,
            action="submit_change_atoms",
            params={"context_id": context_id, "payload": payload},
            operation=operation,
        )
        return ChangeSessionView.model_validate(result)

    def submit_impact_hypotheses(
        self,
        context_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> ChangeSessionView:
        record = self._context_record(context_id)
        context = PreparedContext.model_validate(record["context"])
        self._require_purpose(context, "impact-hypothesis")
        try:
            submission = HostImpactSubmission.model_validate(payload)
        except ValidationError as error:
            self._log_schema_violation(context, error)
            raise ValueError("Host Impact output did not match the required schema") from error
        change_id = record["change_id"]
        if submission.change_id != change_id:
            self._log_warning(context, "change_id_mismatch")
            raise ValueError("Host Impact output used an unexpected change_id")
        candidates = {
            (item["candidate_node_id"], item["atom_id"]): item
            for item in context.payload.get("candidates", [])
        }
        atoms = {
            item.atom_id: item
            for item in self.store.read("change_atoms", ChangeAtom)
            if item.change_id == change_id
        }
        persisted_evidence = {
            item.evidence_id for item in self.store.read("evidence", Evidence)
        }
        seen = set()
        for hypothesis in submission.hypotheses:
            if not hypothesis.atom_id:
                matching = [key for key in candidates if key[0] == hypothesis.candidate_node_id]
                if len(matching) == 1:
                    hypothesis.atom_id = matching[0][1]
            key = (hypothesis.candidate_node_id, hypothesis.atom_id)
            candidate = candidates.get(key)
            if not candidate:
                self._log_warning(context, "unknown_candidate_node")
                raise ValueError(
                    f"Unknown or ambiguous prepared candidate/atom: {key}"
                )
            if key in seen:
                raise ValueError("Duplicate candidate/atom hypothesis")
            seen.add(key)
            if hypothesis.atom_id and hypothesis.atom_id not in atoms:
                self._log_warning(context, "unknown_change_atom")
                raise ValueError(f"Unknown Change Atom: {hypothesis.atom_id}")
            allowed_evidence = set(candidate["evidence_ids"])
            if not set(hypothesis.evidence_ids) <= allowed_evidence & persisted_evidence:
                self._log_warning(context, "invalid_evidence_id")
                raise ValueError(
                    "Host Impact output referenced evidence outside its candidate path"
                )
            if hypothesis.relation_ids and not set(hypothesis.relation_ids) <= set(
                candidate["relation_ids"]
            ):
                self._log_warning(context, "invalid_relation_id")
                raise ValueError(
                    "Host Impact output referenced relation outside its candidate path"
                )

        def operation() -> dict[str, Any]:
            current_atoms = [a for a in self.store.read("change_atoms", ChangeAtom)
                             if a.change_id == change_id]
            if record.get("workspace_fingerprint") != workspace_fingerprint(
                self.store, current_atoms
            ):
                raise ValueError("Prepared analysis is stale; prepare the impact context again")
            change_path = Path(record["change_path"])
            body = change_path.read_text(encoding="utf-8") if change_path.is_file() else ""
            if record.get("change_request_hash") != _json_hash(body):
                raise ValueError(
                    "Prepared change request is stale; prepare the impact context again"
                )
            # Retain prior pages for this exact input snapshot; never borrow another run's advice.
            hypothesis_path = self.store.root / "host_impact_results.jsonl"
            saved = self._read_jsonl(hypothesis_path)
            fingerprint = _json_hash([
                record["workspace_fingerprint"], record["change_request_hash"],
            ])
            for hypothesis in submission.hypotheses:
                one = HostImpactSubmission(change_id=change_id, hypotheses=[hypothesis])
                verified = self._verified_impacts(one, candidates, atoms)[0]
                saved = [r for r in saved if not (
                    r["fingerprint"] == fingerprint
                    and r["artifact_id"] == hypothesis.candidate_node_id
                    and r["atom_id"] == hypothesis.atom_id
                )]
                saved.append({"fingerprint": fingerprint,
                              "artifact_id": hypothesis.candidate_node_id,
                              "atom_id": hypothesis.atom_id, "impact": verified.model_dump()})
            self._write_jsonl(hypothesis_path, saved)
            advice = {(r["artifact_id"], r["atom_id"]): Impact.model_validate(r["impact"])
                      for r in saved if r["fingerprint"] == fingerprint}
            impacts = []
            pending = []
            for path in retrieve_impacts(self.store, current_atoms):
                key = (path.node_id, path.atom_id)
                if key in advice:
                    impacts.append(advice[key])
                else:
                    pending.append({"artifact_id": path.node_id, "atom_id": path.atom_id})
            change = ChangeRequest(
                change_id=change_id,
                title=record["title"],
                path=change_path.as_posix(),
                body=body,
                changed_entity_ids=sorted(
                    {term for atom in atoms.values() for term in atom.target_terms}
                ),
            )
            report = persist_analysis_report(
                self.store,
                change=change,
                impacts=impacts,
                atom_ids=sorted(atoms),
                retrieved_paths=[
                    {
                        "node_id": candidate["candidate_node_id"],
                        "relation_ids": candidate["relation_ids"],
                        "evidence_ids": candidate["evidence_ids"],
                    }
                    for candidate in candidates.values()
                ],
                llm_provider=f"host:{self.host.host}",
                llm_model=self.host.model or "unknown",
            )
            run_dir = self.store.root / "runs" / report.run_id
            self.store.write_json(run_dir / "host_submission_coverage.json", {
                "submitted": len(advice), "pending": pending,
                "total": len(advice) + len(pending), "partial": bool(pending),
            })
            if pending:
                report_path = run_dir / "report.md"
                self.store.write_text(report_path, report_path.read_text(encoding="utf-8") +
                                      f"\n- Host hypotheses pending: {len(pending)}\n")
            self._upsert_session(
                change_id=change_id,
                title=record["title"],
                change_path=record["change_path"],
                status="reviewing",
                atom_ids=sorted(atoms),
                impact_run_id=report.run_id,
            )
            self._append_audit(context, payload, submission.hypotheses)
            return self.get_session(change_id).model_dump()

        result = MutationCoordinator(self.store).run(
            idempotency_key=idempotency_key,
            action="submit_impact_hypotheses",
            params={"context_id": context_id, "payload": payload},
            operation=operation,
        )
        return ChangeSessionView.model_validate(result)

    def submit_graph_extraction(
        self,
        context_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> GraphProposal:
        record = self._context_record(context_id)
        context = PreparedContext.model_validate(record["context"])
        self._require_purpose(context, "dirty-excel-region-extraction")
        try:
            result = RegionExtractionResult.model_validate(payload)
        except ValidationError as error:
            self._log_schema_violation(context, error)
            raise ValueError("Host graph output did not match the required schema") from error
        region_id = record["region_id"]
        if result.region_id != region_id:
            self._log_warning(context, "region_id_mismatch")
            raise ValueError("Host graph output used an unexpected region_id")
        allowed = set(context.evidence_ids)
        node_ids = {item.temp_id for item in result.nodes}
        invalid_nodes = [
            item.temp_id
            for item in result.nodes
            if not item.evidence_ids or not set(item.evidence_ids) <= allowed
        ]
        invalid_edges = [
            item.temp_id
            for item in result.edges
            if item.source_temp_id not in node_ids
            or item.target_temp_id not in node_ids
            or not item.evidence_ids
            or not set(item.evidence_ids) <= allowed
        ]
        if invalid_nodes or invalid_edges:
            self._log_warning(
                context,
                "invalid_graph_evidence",
                details=[
                    {"nodes": invalid_nodes, "edges": invalid_edges},
                ],
            )
            raise ValueError("Host graph output contained invalid Evidence or node references")
        proposal = GraphProposal(
            proposal_id=f"proposal_{_sha1_short(region_id)}",
            region_id=region_id,
            extraction_method="llm",
            result=result,
        )

        def operation() -> dict[str, Any]:
            proposals = [
                item
                for item in self.store.read("graph_proposals", GraphProposal)
                if item.proposal_id != proposal.proposal_id
            ]
            self.store.write("graph_proposals", [*proposals, proposal])
            self._append_audit(
                context,
                payload,
                [*result.nodes, *result.edges],
            )
            return proposal.model_dump()

        stored = MutationCoordinator(self.store).run(
            idempotency_key=idempotency_key,
            action="submit_graph_extraction",
            params={"context_id": context_id, "payload": payload},
            operation=operation,
        )
        return GraphProposal.model_validate(stored)

    def get_session(self, change_id: str) -> ChangeSessionView:
        record = self._session_record(change_id)
        atoms = [
            item.model_dump()
            for item in self.store.read("change_atoms", ChangeAtom)
            if item.change_id == change_id
        ]
        if not atoms and not record:
            raise KeyError(f"Unknown change: {change_id}")
        impacts: list[dict[str, Any]] = []
        run_id = record.get("impact_run_id") if record else None
        candidates_path = self.store.root / "runs" / str(run_id) / "candidates.jsonl"
        if run_id and candidates_path.exists():
            impacts = [
                json.loads(line)
                for line in candidates_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        decisions = [
            item.model_dump()
            for item in self.store.read("impact_decisions", ImpactDecision)
            if item.change_id == change_id
        ]
        now = utc_now()
        return ChangeSessionView(
            session_id=record.get("session_id", f"session.{change_id}"),
            project_id=self.project.project_id,
            change_id=change_id,
            title=record.get("title", change_id),
            status=record.get("status", "atoms_ready"),
            change_atoms=atoms,
            impacts=impacts,
            decisions=decisions,
            warnings=record.get("warnings", []),
            created_at=record.get("created_at", now),
            updated_at=record.get("updated_at", now),
        )

    def record_sampling(self, context_id: str, response: BaseModel, *, model: str) -> None:
        record = self._context_record(context_id)
        context = PreparedContext.model_validate(record["context"])
        response_payload = response.model_dump()
        items = (
            response.change_atoms
            if isinstance(response, ChangeAtomExtraction)
            else response.hypotheses
            if isinstance(response, HostImpactSubmission)
            else [*response.nodes, *response.edges]
            if isinstance(response, RegionExtractionResult)
            else []
        )
        with ProjectWriteLock(self.store.root):
            self._append_audit(
                context,
                response_payload,
                items,
                phase="sampling",
                model=model,
            )

    def _prepare(
        self,
        *,
        purpose: str,
        schema_name: str,
        instructions: str,
        payload: dict[str, Any],
        evidence_ids: list[str],
        metadata: dict[str, str],
    ) -> PreparedContext:
        preview = self.approvals.create_preview(
            purpose=purpose,
            host=self.host.host,
            provider=f"host:{self.host.host}",
            model=self.host.model or "unknown",
            payload=payload,
            evidence_ids=evidence_ids,
            external=self.host.external,
        )
        context = PreparedContext(
            context_id=f"context-{uuid4().hex}",
            project_id=self.project.project_id,
            purpose=purpose,
            schema_name=schema_name,
            instructions=instructions,
            payload=redact_payload(payload),
            evidence_ids=evidence_ids,
            source_hash=preview.source_hash,
            transmission_preview=preview,
        )
        record = {
            "context": context.model_dump(),
            "host_context": self.host.model_dump(),
            **metadata,
        }
        with ProjectWriteLock(self.store.root):
            records = self._read_jsonl(self.context_path)
            records.append(record)
            self._write_jsonl(self.context_path, records)
        if preview.required:
            return context.model_copy(
                update={
                    "payload": {
                        "withheld": True,
                        "reason": "external_transmission_approval_required",
                        "preview_id": preview.preview_id,
                        "approval_url": (
                            f"http://127.0.0.1:8765/approval/{preview.preview_id}"
                            f"?project_id={self.project.project_id}"
                        ),
                    }
                }
            )
        return context

    def _verified_impacts(
        self,
        submission: HostImpactSubmission,
        candidates: dict[tuple[str, str], dict[str, Any]],
        atoms: dict[str, ChangeAtom],
    ) -> list[Impact]:
        artifacts = {item.artifact_id: item for item in self.store.read("artifacts", Artifact)}
        relations = {item.relation_id: item for item in self.store.read("relations", Relation)}
        impacts = []
        for hypothesis in submission.hypotheses:
            candidate = candidates[(hypothesis.candidate_node_id, hypothesis.atom_id)]
            artifact = artifacts[hypothesis.candidate_node_id]
            atom = atoms[hypothesis.atom_id]
            relation_path = [
                relations[relation_id]
                for relation_id in candidate["relation_ids"]
                if relation_id in relations
            ]
            priority, verifier_reason = classify_impact(
                self.store,
                relation_path,
                hypothesis.evidence_ids,
                atom.target_terms,
                atom.before,
                change_property=atom.property,
                artifact_type=artifact.artifact_type,
            )
            suggestion = hypothesis.review_priority_suggestion
            if suggestion and PRIORITY_ORDER[suggestion] > PRIORITY_ORDER[priority]:
                priority = suggestion
            impacts.append(
                Impact(
                    artifact_id=artifact.artifact_id,
                    display_name=artifact.display_name,
                    artifact_type=artifact.artifact_type,
                    review_priority=priority,
                    evidence_strength=grounding_strength(
                        self.store, relation_path, hypothesis.evidence_ids
                    ),
                    match_type="exact" if priority == "must_review" else "semantic",
                    relation_distance=len(relation_path),
                    rule_assessment=(
                        "explicit_relation"
                        if any(item.polarity == "explicit" for item in relation_path)
                        else "inferred_relation"
                    ),
                    reason=f"{hypothesis.reason} Verifier: {verifier_reason}",
                    relation_paths=[
                        " -> ".join(
                            f"{item.source_id} -{item.relation_type}-> {item.target_id}"
                            for item in relation_path
                        )
                    ],
                    evidence_ids=hypothesis.evidence_ids,
                    relation_statuses=sorted({item.status for item in relation_path}),
                    needs_review=priority != "hidden",
                    llm_reason=hypothesis.reason,
                    selected_evidence_ids=hypothesis.evidence_ids,
                    impact_type=hypothesis.impact_type,
                    required_actions=hypothesis.required_actions,
                    warnings=hypothesis.warnings,
                    uncertainty=hypothesis.uncertainty,
                )
            )
        return sorted(
            impacts,
            key=lambda item: (PRIORITY_ORDER[item.review_priority], item.artifact_id),
        )

    def _append_audit(
        self,
        context: PreparedContext,
        response: dict[str, Any],
        items: list[Any],
        *,
        phase: str = "submit",
        model: str | None = None,
    ) -> None:
        preview = context.transmission_preview
        evidence_ids = sorted(
            {
                evidence_id
                for item in items
                for evidence_id in getattr(item, "evidence_ids", [])
            }
        )
        row = {
            "event": "llm",
            "provider": f"host:{self.host.host}",
            "host": self.host.host,
            "model": model or self.host.model or "unknown",
            "purpose": context.purpose,
            "phase": phase,
            "item_count": len(items),
            "redacted": bool(preview and preview.redacted),
            "source_hash": context.source_hash,
            "prompt_hash": _json_hash(context.payload),
            "response_hash": _json_hash(response),
            "evidence_ids": evidence_ids,
            "created_at": utc_now(),
        }
        path = self.store.root / "trace.jsonl"
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        self.store.write_text(path, existing + json.dumps(row, ensure_ascii=False) + "\n")

    def _upsert_session(
        self,
        *,
        change_id: str,
        title: str,
        change_path: str,
        status: str,
        atom_ids: list[str],
        impact_run_id: str | None = None,
    ) -> None:
        records = self._read_jsonl(self.session_path)
        current = next((item for item in records if item["change_id"] == change_id), None)
        now = utc_now()
        if current is None:
            current = {
                "session_id": f"session-{uuid4().hex}",
                "project_id": self.project.project_id,
                "change_id": change_id,
                "created_at": now,
            }
            records.append(current)
        current.update(
            {
                "title": title,
                "change_path": change_path,
                "status": status,
                "atom_ids": atom_ids,
                "updated_at": now,
            }
        )
        if impact_run_id:
            current["impact_run_id"] = impact_run_id
        self._write_jsonl(self.session_path, records)

    def _session_record(self, change_id: str) -> dict[str, Any]:
        return next(
            (
                item
                for item in self._read_jsonl(self.session_path)
                if item["change_id"] == change_id
            ),
            {},
        )

    def _context_record(self, context_id: str) -> dict[str, Any]:
        record = next(
            (
                item
                for item in self._read_jsonl(self.context_path)
                if item["context"]["context_id"] == context_id
            ),
            None,
        )
        if not record:
            raise KeyError(f"Unknown prepared context: {context_id}")
        if record["context"]["project_id"] != self.project.project_id:
            raise ValueError("Prepared context belongs to another project")
        return record

    def _require_initialized(self) -> None:
        if not (self.store.root / "config.yml").is_file():
            raise ValueError("SpecImpact is not initialized")

    @staticmethod
    def _require_purpose(context: PreparedContext, purpose: str) -> None:
        if context.purpose != purpose:
            raise ValueError(f"Prepared context is not for {purpose}")

    def _log_schema_violation(self, context: PreparedContext, error: ValidationError) -> None:
        details = [
            {"location": list(item["loc"]), "type": item["type"]} for item in error.errors()
        ]
        self._log_warning(context, "schema_violation", details=details)

    def _log_warning(
        self,
        context: PreparedContext,
        code: str,
        *,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        row = {
            "event": "host_output_warning",
            "context_id": context.context_id,
            "purpose": context.purpose,
            "provider": f"host:{self.host.host}",
            "code": code,
            "details": details or [],
            "created_at": utc_now(),
        }
        with ProjectWriteLock(self.store.root):
            records = self._read_jsonl(self.warning_path)
            records.append(row)
            self._write_jsonl(self.warning_path, records)

    @staticmethod
    def _read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def _write_jsonl(self, path: Path, records: list[dict[str, Any]]) -> None:
        content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
        self.store.write_text(path, content)


def _title(body: str) -> str:
    return next(
        (line.lstrip("# ").strip() for line in body.splitlines() if line.strip()),
        "Host Change Request",
    )


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _sha1_short(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]


def _json_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
