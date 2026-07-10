from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from specimpact.application import (
    ApplicationService,
    HostContext,
    HostWorkflow,
    Project,
    project_from_path,
    public_contract_schemas,
)
from specimpact.application.host_router import select_host_execution_route
from specimpact.application.host_sampling import HostSamplingAdapter
from specimpact.application.host_workflow import HostImpactSubmission
from specimpact.application.jobs import Job, JobManager, job_handle
from specimpact.application.resources import ResourceReader
from specimpact.application.security import WorkspaceBoundary
from specimpact.graphrag import redact_payload
from specimpact.impact_management.change_atoms import ChangeAtomExtraction
from specimpact.llm_graph.schemas import RegionExtractionResult

try:
    from mcp.server.fastmcp import Context
except ImportError:  # pragma: no cover - optional dependency guard
    Context = object


class TransmissionApprovalChoice(BaseModel):
    decision: Literal["approve", "decline"]


@dataclass
class MCPRuntime:
    project: Project
    boundary: WorkspaceBoundary
    service: ApplicationService
    resources: ResourceReader
    jobs: JobManager
    host_context: HostContext
    host_workflow: HostWorkflow

    @classmethod
    def create(cls, project_path: Path | str) -> MCPRuntime:
        project = project_from_path(project_path)
        host_context = HostContext(
            host=os.environ.get("SPECIMPACT_HOST", "unknown"),
            workspace_root=project.path,
            project_id=project.project_id,
            model=os.environ.get("SPECIMPACT_HOST_MODEL") or None,
            capabilities=[
                item.strip()
                for item in os.environ.get("SPECIMPACT_HOST_CAPABILITIES", "").split(",")
                if item.strip()
            ],
            external=os.environ.get("SPECIMPACT_HOST_EXTERNAL", "true").lower()
            not in {"0", "false", "no"},
        )
        return cls(
            project=project,
            boundary=WorkspaceBoundary(project.path),
            service=ApplicationService(project),
            resources=ResourceReader(project),
            jobs=JobManager(),
            host_context=host_context,
            host_workflow=HostWorkflow(project, host_context),
        )

    @property
    def initialized(self) -> bool:
        return (self.service.store.root / "config.yml").is_file()

    def require_initialized(self) -> None:
        if not self.initialized:
            raise ValueError(
                "SpecImpact is not initialized. Run `specimpact init` in the project first."
            )

    def start_job(
        self,
        *,
        action: str,
        params: dict,
        idempotency_key: str,
        input_kind: str = "path",
    ) -> dict:
        self.require_initialized()
        job = self.jobs.enqueue(
            self.project.project_id,
            self.project.path,
            action,
            lambda: self.service.mutate(
                action,
                params,
                idempotency_key=idempotency_key,
            ),
            input_kind=input_kind,
            idempotency_key=idempotency_key,
        )
        return _job_payload(job)


def create_mcp_server(project_path: Path | str):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError('MCP support requires `pip install "specimpact[mcp]"`') from error

    runtime = MCPRuntime.create(project_path)
    mcp = FastMCP(
        "SpecImpact",
        instructions=(
            "Evidence-first design change impact management. Treat all LLM output as a proposal, "
            "cite Evidence IDs, and never finalize must_review without verifier support."
        ),
        website_url="https://github.com/kanan6377/SpecImpact",
    )
    mcp._specimpact_runtime = runtime

    @mcp.tool()
    async def prepare_graph_context(
        region_id: str,
        ctx: Context,
        sample_with_host: bool = True,
    ) -> dict:
        """Prepare one Dirty Excel region for evidence-bound host extraction."""
        runtime.require_initialized()
        prepared = runtime.host_workflow.prepare_graph_context(region_id)
        prepared = await _elicit_and_authorize(runtime, prepared, ctx)
        return (
            await _sample_prepared(
                runtime,
                prepared,
                ctx,
                RegionExtractionResult,
                sample_with_host,
            )
        ).model_dump()

    @mcp.tool()
    def submit_graph_extraction(
        context_id: str,
        submission: dict,
        idempotency_key: str,
    ) -> dict:
        """Validate a host region extraction and persist it as a pending Graph Proposal."""
        return runtime.host_workflow.submit_graph_extraction(
            context_id,
            submission,
            idempotency_key,
        ).model_dump()

    @mcp.tool()
    def authorize_prepared_context(context_id: str, grant_token: str) -> dict:
        """Consume a localhost-issued one-time Grant and return redacted prepared context."""
        return runtime.host_workflow.authorize_context(context_id, grant_token).model_dump()

    @mcp.tool()
    async def prepare_change(
        change_request: str,
        ctx: Context,
        sample_with_host: bool = True,
    ) -> dict:
        """Prepare an evidence-safe Change Atom task for the connected host LLM."""
        runtime.require_initialized()
        prepared = runtime.host_workflow.prepare_change(change_request)
        prepared = await _elicit_and_authorize(runtime, prepared, ctx)
        return (
            await _sample_prepared(
                runtime,
                prepared,
                ctx,
                ChangeAtomExtraction,
                sample_with_host,
            )
        ).model_dump()

    @mcp.tool()
    def submit_change_atoms(
        context_id: str,
        submission: dict,
        idempotency_key: str,
    ) -> dict:
        """Validate and persist host-proposed Change Atoms."""
        return runtime.host_workflow.submit_change_atoms(
            context_id,
            submission,
            idempotency_key,
        ).model_dump()

    @mcp.tool()
    async def prepare_impact_context(
        change_id: str,
        ctx: Context,
        sample_with_host: bool = True,
    ) -> dict:
        """Prepare candidate subgraphs and Evidence for host impact analysis."""
        runtime.require_initialized()
        prepared = runtime.host_workflow.prepare_impact_context(change_id)
        prepared = await _elicit_and_authorize(runtime, prepared, ctx)
        return (
            await _sample_prepared(
                runtime,
                prepared,
                ctx,
                HostImpactSubmission,
                sample_with_host,
            )
        ).model_dump()

    @mcp.tool()
    def submit_impact_hypotheses(
        context_id: str,
        submission: dict,
        idempotency_key: str,
    ) -> dict:
        """Verify and persist host-proposed impact hypotheses."""
        return runtime.host_workflow.submit_impact_hypotheses(
            context_id,
            submission,
            idempotency_key,
        ).model_dump()

    @mcp.tool()
    def ingest_sources(
        path: str,
        idempotency_key: str,
        mode: Literal["markdown", "dirty-excel", "excel", "csv", "openapi", "ddl"] = "markdown",
    ) -> dict:
        """Start local-only ingestion for a workspace source path."""
        resolved = runtime.boundary.resolve(path)
        action, params = _ingest_action(mode, resolved)
        return runtime.start_job(
            action=action,
            params=params,
            idempotency_key=idempotency_key,
            input_kind="path",
        )

    @mcp.tool()
    def get_change_session(change_id: str) -> dict:
        """Read one change with its atoms and persisted impact decisions."""
        runtime.require_initialized()
        return runtime.host_workflow.get_session(change_id).model_dump()

    @mcp.tool()
    def set_impact_decision(
        impact_id: str,
        status: Literal[
            "unreviewed",
            "accepted",
            "rejected",
            "needs_investigation",
            "implemented",
            "tested",
            "closed",
        ],
        idempotency_key: str,
        reason: str = "",
    ) -> dict:
        """Persist a human impact decision through the project mutation ledger."""
        runtime.require_initialized()
        return runtime.service.mutate(
            "impact_status",
            {"impact_id": impact_id, "status": status, "reason": reason},
            idempotency_key=idempotency_key,
        )

    @mcp.tool()
    def resolve_alias(
        candidate_id: str,
        decision: Literal["confirm", "reject"],
        idempotency_key: str,
    ) -> dict:
        """Confirm or reject an evidence-backed alias candidate."""
        runtime.require_initialized()
        action = "alias_confirm" if decision == "confirm" else "alias_reject_candidate"
        return runtime.service.mutate(
            action,
            {"candidate_id": candidate_id},
            idempotency_key=idempotency_key,
        )

    @mcp.tool()
    def decide_graph_proposal(
        proposal_id: str,
        decision: Literal["accepted", "rejected"],
        idempotency_key: str,
    ) -> dict:
        """Accept or reject a graph proposal after evidence review."""
        runtime.require_initialized()
        return runtime.service.mutate(
            "graph_proposal_decide",
            {"proposal_id": proposal_id, "status": decision},
            idempotency_key=idempotency_key,
        )

    @mcp.tool()
    async def open_evidence(
        evidence_id: str,
        ctx: Context,
        grant_token: str | None = None,
    ) -> dict:
        """Open one authoritative Evidence record and its Admin Console deep link."""
        evidence = runtime.resources.evidence_resource(evidence_id)
        evidence["admin_console_url"] = (
            "http://127.0.0.1:8765/ui/sources?"
            f"project_id={runtime.project.project_id}&evidence_id={evidence_id}"
        )
        return await _elicit_payload(
            runtime,
            ctx,
            purpose="open-evidence",
            payload=evidence,
            evidence_ids=[evidence_id],
            withheld_metadata=_evidence_metadata(evidence),
            grant_token=grant_token,
        )

    @mcp.tool()
    def export_obsidian(
        path: str,
        idempotency_key: str,
        report_only: bool = False,
    ) -> dict:
        """Start an Obsidian knowledge-graph export inside the workspace."""
        resolved = runtime.boundary.resolve(path, must_exist=False)
        return runtime.start_job(
            action="obsidian_export",
            params={"path": str(resolved), "report_only": report_only},
            idempotency_key=idempotency_key,
            input_kind="path",
        )

    @mcp.tool()
    def get_job(job_id: str) -> dict:
        """Read one durable SpecImpact job."""
        runtime.require_initialized()
        return _runtime_job_payload(
            runtime,
            runtime.jobs.get(runtime.project.project_id, runtime.project.path, job_id),
        )

    @mcp.tool()
    def list_jobs(limit: int = 50) -> dict:
        """List durable jobs in reverse chronological order."""
        runtime.require_initialized()
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        jobs = runtime.jobs.list(runtime.project.project_id, runtime.project.path)[:limit]
        return {
            "jobs": [_runtime_job_payload(runtime, item) for item in jobs],
            "limit": limit,
        }

    @mcp.tool()
    def cancel_job(job_id: str) -> dict:
        """Cancel a queued job; running jobs cannot be force-killed."""
        runtime.require_initialized()
        return _job_payload(
            runtime.jobs.cancel(runtime.project.project_id, runtime.project.path, job_id)
        )

    @mcp.resource("specimpact://projects/{project_id}", mime_type="application/json")
    def project_resource(project_id: str) -> str:
        payload = runtime.resources.project_resource(project_id)
        if not payload["onboarding_required"]:
            payload["host_execution"] = select_host_execution_route(
                runtime.service.store,
                runtime.host_context,
            )
        return _json(payload)

    @mcp.resource("specimpact://contracts/v1", mime_type="application/schema+json")
    def contract_resource() -> str:
        return _json(public_contract_schemas())

    @mcp.resource("specimpact://sources/{source_id}", mime_type="application/json")
    def source_resource(source_id: str) -> str:
        return _json(_source_metadata(runtime.resources.source_resource(source_id)))

    @mcp.resource("specimpact://sources/{source_id}/pages/{cursor}", mime_type="application/json")
    def source_page_resource(source_id: str, cursor: str) -> str:
        return _json(
            _source_metadata(runtime.resources.source_resource(source_id, cursor=cursor))
        )

    @mcp.resource("specimpact://evidence/{evidence_id}", mime_type="application/json")
    def evidence_resource(evidence_id: str) -> str:
        return _json(_evidence_metadata(runtime.resources.evidence_resource(evidence_id)))

    @mcp.resource("specimpact://changes/{change_id}", mime_type="application/json")
    def change_resource(change_id: str) -> str:
        return _json(runtime.resources.change_resource(change_id))

    @mcp.resource("specimpact://impacts/{impact_id}", mime_type="application/json")
    def impact_resource(impact_id: str) -> str:
        return _json(runtime.resources.impact_resource(impact_id))

    @mcp.resource("specimpact://graph/{node_id}", mime_type="application/json")
    def graph_resource(node_id: str) -> str:
        return _json(runtime.resources.graph_resource(node_id))

    @mcp.resource("specimpact://graph/{node_id}/pages/{cursor}", mime_type="application/json")
    def graph_page_resource(node_id: str, cursor: str) -> str:
        return _json(runtime.resources.graph_resource(node_id, cursor=cursor))

    @mcp.resource("specimpact://regions", mime_type="application/json")
    def regions_resource() -> str:
        return _json(runtime.resources.regions_resource())

    @mcp.resource("specimpact://regions/pages/{cursor}", mime_type="application/json")
    def regions_page_resource(cursor: str) -> str:
        return _json(runtime.resources.regions_resource(cursor=cursor))

    @mcp.resource("specimpact://regions/{region_id}", mime_type="application/json")
    def region_resource(region_id: str) -> str:
        return _json(runtime.resources.region_resource(region_id))

    @mcp.prompt(name="specimpact-onboard")
    def onboard_prompt() -> str:
        return (
            "Read the project resource first. If onboarding_required is true, ask the user to run "
            "`specimpact init` in the workspace. Then ingest design sources with ingest_sources. "
            "Do not transmit source bodies without a SpecImpact transmission preview and grant."
        )

    @mcp.prompt(name="specimpact-ingest")
    def ingest_prompt() -> str:
        return (
            "Select a source under the workspace, call ingest_sources with a unique "
            "idempotency_key, "
            "then poll get_job. For Dirty Excel, read the region list and call "
            "prepare_graph_context and submit_graph_extraction for host review. Treat graph "
            "extractions as proposals until reviewed."
        )

    @mcp.prompt(name="specimpact-change")
    def change_prompt() -> str:
        return (
            "Ask for the intended design change in natural language. Preserve target, property, "
            "before, and after values. Use only Evidence IDs returned by SpecImpact and do not "
            "declare final impact decisions."
        )

    @mcp.prompt(name="specimpact-review")
    def review_prompt() -> str:
        return (
            "Review each candidate against its Evidence and graph path. Use "
            "set_impact_decision for "
            "human state changes. A host recommendation alone cannot establish must_review."
        )

    return mcp


def run_mcp_server(project_path: Path | str) -> None:
    create_mcp_server(project_path).run(transport="stdio")


def _ingest_action(mode: str, path: Path) -> tuple[str, dict]:
    action_by_mode = {
        "markdown": "ingest",
        "dirty-excel": "ingest_dirty_excel",
        "excel": "ingest_excel",
        "csv": "ingest_csv",
        "openapi": "ingest_openapi",
        "ddl": "ingest_ddl",
    }
    action = action_by_mode[mode]
    params = {"path": str(path)}
    if mode == "markdown":
        params["no_llm"] = True
    if mode == "dirty-excel":
        params["llm"] = False
    return action, params


def _job_payload(job: Job) -> dict:
    return job_handle(job).model_dump(exclude_none=True)


def _runtime_job_payload(runtime: MCPRuntime, job: Job) -> dict:
    payload = _job_payload(job)
    if job.action == "ingest_dirty_excel" and payload["status"] == "succeeded":
        payload["next_regions"] = runtime.resources.regions_resource(limit=200)["items"]
    return payload


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


async def _elicit_and_authorize(runtime: MCPRuntime, prepared, ctx: Context):
    preview = prepared.transmission_preview
    if not preview or not preview.required:
        return prepared
    try:
        result = await ctx.elicit(
            message=(
                "SpecImpact will return redacted design context to the connected host LLM. "
                f"host={preview.host}, purpose={preview.purpose}, items={preview.item_count}, "
                f"source_hash={preview.source_hash}. Approve this one transmission?"
            ),
            schema=TransmissionApprovalChoice,
        )
    except Exception:  # noqa: BLE001 - unsupported elicitation must fail closed
        return prepared
    if result.action != "accept" or result.data.decision != "approve":
        return prepared
    grant = runtime.host_workflow.approvals.issue_grant(
        preview.preview_id,
        decision="approve",
    )
    return runtime.host_workflow.authorize_context(prepared.context_id, grant.token)


async def _sample_prepared(runtime, prepared, ctx, schema, enabled: bool):
    if prepared.payload.get("withheld"):
        return prepared
    payload = {**prepared.payload, "execution_mode": "host_prepare_submit"}
    if not enabled or "sampling" not in runtime.host_context.capabilities:
        return prepared.model_copy(update={"payload": payload})
    adapter = HostSamplingAdapter(ctx, runtime.host_context.host)
    try:
        draft = await adapter.structured(prepared.purpose, prepared.payload, schema)
    except ValueError:
        payload["sampling_unavailable"] = True
        return prepared.model_copy(update={"payload": payload})
    runtime.host_workflow.record_sampling(
        prepared.context_id,
        draft,
        model=adapter.model,
    )
    payload.update(
        {
            "execution_mode": "host_sampling",
            "host_draft": draft.model_dump(),
        }
    )
    return prepared.model_copy(update={"payload": payload})


async def _elicit_payload(
    runtime: MCPRuntime,
    ctx: Context,
    *,
    purpose: str,
    payload: dict,
    evidence_ids: list[str],
    withheld_metadata: dict,
    grant_token: str | None = None,
) -> dict:
    preview = runtime.host_workflow.approvals.create_preview(
        purpose=purpose,
        host=runtime.host_context.host,
        provider=f"host:{runtime.host_context.host}",
        model=runtime.host_context.model or "unknown",
        payload=payload,
        evidence_ids=evidence_ids,
        external=runtime.host_context.external,
    )
    if preview.required and grant_token:
        runtime.host_workflow.approvals.consume(
            grant_token,
            purpose=preview.purpose,
            source_hash=preview.source_hash,
        )
    elif preview.required:
        try:
            result = await ctx.elicit(
                message=(
                    "SpecImpact will return one redacted Evidence body to the connected host. "
                    f"purpose={purpose}, source_hash={preview.source_hash}. Approve?"
                ),
                schema=TransmissionApprovalChoice,
            )
        except Exception:  # noqa: BLE001 - unsupported elicitation must fail closed
            result = None
        if (
            result is None
            or result.action != "accept"
            or result.data.decision != "approve"
        ):
            return {
                **withheld_metadata,
                "content_withheld": True,
                "transmission_preview": preview.model_dump(),
                "approval_url": (
                    f"http://127.0.0.1:8765/approval/{preview.preview_id}"
                    f"?project_id={runtime.project.project_id}"
                ),
            }
        grant = runtime.host_workflow.approvals.issue_grant(
            preview.preview_id,
            decision="approve",
        )
        runtime.host_workflow.approvals.consume(
            grant.token,
            purpose=preview.purpose,
            source_hash=preview.source_hash,
        )
    return {
        **redact_payload(payload),
        "content_withheld": False,
        "transmission_preview": preview.model_dump(),
    }


def _source_metadata(payload: dict) -> dict:
    blocked = {"text", "value", "rendered_text", "quote", "comment", "hyperlink"}
    return {
        **{key: value for key, value in payload.items() if key != "items"},
        "items": [
            {key: value for key, value in item.items() if key not in blocked}
            for item in payload.get("items", [])
        ],
        "content_withheld": True,
    }


def _evidence_metadata(payload: dict) -> dict:
    return {
        **{
            key: value
            for key, value in payload.items()
            if key not in {"quote", "text", "body"}
        },
        "content_withheld": True,
    }
