from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from specimpact.application import ApplicationService, public_contract_schemas
from specimpact.application.approval import ApprovalManager
from specimpact.core import latest_run_dir
from specimpact.reports import export_report_excel
from specimpact.source_freshness import freshness_data
from specimpact.webui.jobs import JobManager
from specimpact.webui.registry import Project, ProjectRegistry
from specimpact.webui.services import (
    MUTATING_ACTIONS,
    aliases_data,
    copy_demo,
    demo_source,
    design_documents_data,
    dirty_excel_data,
    evidence_data,
    external_preview,
    graph_data,
    impact_decisions_data,
    integration_data,
    project_overview,
    report_data,
    review_queue_data,
    run_history,
    source_library_data,
    store_for,
    tool_result,
)
from specimpact.webui.uploads import save_uploads

PAGES = {
    "dashboard",
    "sources",
    "impact-board",
    "graph",
    "reviews",
    "vault",
    "jobs",
    "settings",
}
LEGACY_PAGES = {
    "demo": "dashboard",
    "ingest": "sources",
    "dirty-excel": "sources",
    "analyze": "impact-board",
    "aliases": "reviews",
    "tools": "jobs",
}
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"


class ProjectRequest(BaseModel):
    path: str
    display_name: str | None = None
    create: bool = False


class JobRequest(BaseModel):
    action: str
    params: dict = Field(default_factory=dict)
    input_kind: Literal["path", "upload", "demo", "settings"] = "path"
    external_approved: bool = False
    idempotency_key: str | None = None


class UploadFileRequest(BaseModel):
    filename: str
    content_base64: str


class UploadRequest(BaseModel):
    workflow: str
    files: list[UploadFileRequest]


class ToolRequest(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


def create_app(
    *,
    registry_root: Path | str | None = None,
    allow_test_hosts: bool = False,
    session_ttl_seconds: float = 60 * 60,
    max_sessions: int = 256,
) -> FastAPI:
    if session_ttl_seconds <= 0:
        raise ValueError("session_ttl_seconds must be positive")
    if max_sessions <= 0:
        raise ValueError("max_sessions must be positive")
    app = FastAPI(title="SpecImpact GUI", docs_url=None, redoc_url=None)
    app.state.registry = ProjectRegistry(registry_root)
    app.state.jobs = JobManager()
    app.state.sessions = {}
    app.state.session_lock = threading.RLock()
    app.state.session_ttl_seconds = session_ttl_seconds
    app.state.max_sessions = max_sessions
    app.state.allow_test_hosts = allow_test_hosts
    templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.middleware("http")
    async def localhost_only(request: Request, call_next):
        host = request.headers.get("host", "")
        if not _loopback_host(host, allow_test_hosts=app.state.allow_test_hosts):
            return JSONResponse({"detail": "SpecImpact GUI is localhost-only"}, status_code=403)
        if request.url.path.startswith("/api/") and request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            rejection = _mutation_rejection(request, app)
            if rejection:
                return JSONResponse({"detail": rejection}, status_code=403)
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"page": "dashboard", "pages": PAGES},
        )

    @app.get("/ui/{page}", response_class=HTMLResponse)
    def page(request: Request, page: str):
        if page in LEGACY_PAGES:
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(f"/ui/{LEGACY_PAGES[page]}{query}", status_code=307)
        if page not in PAGES:
            raise HTTPException(status_code=404, detail="Unknown page")
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"page": page, "pages": PAGES},
        )

    @app.get("/approval/{preview_id}", response_class=HTMLResponse)
    def approval_page(request: Request, preview_id: str, project_id: str):
        project = _project(app, project_id)
        try:
            preview = ApprovalManager(project).get_preview(preview_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return templates.TemplateResponse(
            request=request,
            name="approval.html",
            context={"project": project, "preview": preview},
        )

    @app.get("/api/session")
    def session(request: Request):
        token = request.cookies.get("specimpact_session")
        with app.state.session_lock:
            _prune_sessions(app)
            if token not in app.state.sessions:
                _make_session_room(app)
                token = secrets.token_urlsafe(32)
            app.state.sessions[token] = time.monotonic()
        response = JSONResponse({"csrf_token": token})
        response.set_cookie(
            "specimpact_session",
            token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return response

    @app.get("/api/projects")
    def projects():
        return {"projects": [item.model_dump() for item in app.state.registry.list()]}

    @app.get("/api/contracts/v1")
    def contracts_v1():
        return {"version": "v1", "schemas": public_contract_schemas()}

    @app.post(
        "/api/projects/{project_id}/transmission-previews/{preview_id}/approve"
    )
    def approve_transmission(project_id: str, preview_id: str):
        project = _project(app, project_id)
        try:
            grant = ApprovalManager(project).issue_grant(preview_id, decision="approve")
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "grant": grant.model_dump(),
            "instruction": "Pass this token once to authorize_prepared_context.",
        }

    @app.post("/api/projects")
    def add_project(body: ProjectRequest):
        try:
            project = app.state.registry.add(
                body.path,
                display_name=body.display_name,
                create=body.create,
            )
            app.state.jobs.register_project(project.project_id, project.path)
            return {"project": project.model_dump()}
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.delete("/api/projects/{project_id}")
    def remove_project(project_id: str):
        try:
            app.state.registry.remove(project_id)
            return {"removed": project_id}
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/demo")
    def create_demo():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = app.state.registry.root / "demo-workspaces" / f"{timestamp}-{secrets.token_hex(3)}"
        try:
            copy_demo(demo_source(), target)
            project = app.state.registry.add(target, display_name=f"ガイド付きサンプル {timestamp}")
            return {"project": project.model_dump()}
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/overview")
    def overview(project_id: str):
        return project_overview(_project(app, project_id))

    @app.get("/api/projects/{project_id}/jobs")
    def jobs(project_id: str):
        project = _project(app, project_id)
        return {
            "jobs": [
                item.model_dump()
                for item in app.state.jobs.list(project.project_id, project.path)
            ]
        }

    @app.get("/api/projects/{project_id}/jobs/{job_id}")
    def job(project_id: str, job_id: str):
        project = _project(app, project_id)
        try:
            return app.state.jobs.get(project.project_id, project.path, job_id).model_dump()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/jobs")
    def enqueue(project_id: str, body: JobRequest):
        project = _project(app, project_id)
        if body.action not in MUTATING_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unknown GUI action: {body.action}")
        params = {**body.params, "external_approved": body.external_approved}
        try:
            preview = external_preview(project, body.action, params)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if preview["required"] and not body.external_approved:
            raise HTTPException(
                status_code=400,
                detail={"message": "外部送信の承認が必要です。", **preview},
            )
        idempotency_key = body.idempotency_key or secrets.token_urlsafe(24)
        created = app.state.jobs.enqueue(
            project.project_id,
            project.path,
            body.action,
            lambda: ApplicationService(project).mutate(
                body.action,
                params,
                idempotency_key=idempotency_key,
            ),
            input_kind=body.input_kind,
            idempotency_key=idempotency_key,
        )
        return {"job": created.model_dump()}

    @app.post("/api/projects/{project_id}/jobs/{job_id}/cancel")
    def cancel_job(project_id: str, job_id: str):
        project = _project(app, project_id)
        try:
            return app.state.jobs.cancel(project.project_id, project.path, job_id).model_dump()
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/projects/{project_id}/uploads")
    def uploads(project_id: str, body: UploadRequest):
        project = _project(app, project_id)
        try:
            files = [
                (item.filename, base64.b64decode(item.content_base64, validate=True))
                for item in body.files
            ]
            paths = save_uploads(project.path, body.workflow, files)
            return {"paths": [str(path) for path in paths]}
        except (ValueError, binascii.Error) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/external-preview")
    def preview(project_id: str, action: str, params: str = "{}"):
        project = _project(app, project_id)
        try:
            value = json.loads(params)
            if not isinstance(value, dict):
                raise ValueError("params must contain a JSON object")
            return external_preview(project, action, value)
        except (json.JSONDecodeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/graph")
    def graph(
        project_id: str,
        item_type: str | None = None,
        status: str | None = None,
        extraction_method: str | None = None,
    ):
        return graph_data(
            _project(app, project_id),
            item_type=item_type,
            status=status,
            extraction_method=extraction_method,
        )

    @app.get("/api/projects/{project_id}/evidence")
    def evidence(project_id: str, evidence_id: list[str] | None = Query(None)):
        return {"evidence": evidence_data(_project(app, project_id), evidence_id)}

    @app.get("/api/projects/{project_id}/design-documents")
    def design_documents(project_id: str, evidence_id: list[str] | None = Query(None)):
        return design_documents_data(_project(app, project_id), evidence_id)

    @app.get("/api/projects/{project_id}/sources")
    def sources(project_id: str):
        return source_library_data(_project(app, project_id))

    @app.get("/api/projects/{project_id}/report")
    def report(project_id: str):
        try:
            return report_data(_project(app, project_id))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/runs")
    def runs(project_id: str):
        return {"runs": run_history(_project(app, project_id))}

    @app.get("/api/projects/{project_id}/aliases")
    def aliases(project_id: str):
        return aliases_data(_project(app, project_id))

    @app.get("/api/projects/{project_id}/dirty-excel")
    def dirty_excel(project_id: str):
        return dirty_excel_data(_project(app, project_id))

    @app.get("/api/projects/{project_id}/impact-decisions")
    def impact_decisions(project_id: str, change_id: str | None = None):
        return {"decisions": impact_decisions_data(_project(app, project_id), change_id)}

    @app.get("/api/projects/{project_id}/reviews")
    def reviews(project_id: str):
        return review_queue_data(_project(app, project_id))

    @app.get("/api/projects/{project_id}/freshness")
    def freshness(project_id: str):
        return freshness_data(store_for(_project(app, project_id)))

    @app.get("/api/projects/{project_id}/integrations")
    def integrations(project_id: str):
        return integration_data(_project(app, project_id))

    @app.post("/api/projects/{project_id}/tool")
    def read_only_tool(project_id: str, body: ToolRequest):
        try:
            return {"result": tool_result(_project(app, project_id), body.tool, body.params)}
        except (KeyError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/projects/{project_id}/download/{format}")
    def download(project_id: str, format: str):
        project = _project(app, project_id)
        try:
            run_dir = latest_run_dir(store_for(project))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if format not in {"markdown", "json", "excel"}:
            raise HTTPException(status_code=400, detail="format must be markdown, json, or excel")
        if format == "excel":
            path = export_report_excel(store_for(project))
            return FileResponse(path, filename="report.xlsx")
        name = "report.md" if format == "markdown" else "report.json"
        return FileResponse(run_dir / name, filename=name)

    return app


def _project(app: FastAPI, project_id: str) -> Project:
    try:
        return app.state.registry.get(project_id, touch=True)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _mutation_rejection(request: Request, app: FastAPI) -> str | None:
    host = request.headers.get("host", "")
    origin = request.headers.get("origin")
    if not origin:
        return "Origin header is required"
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not _loopback_host(
        parsed.netloc, allow_test_hosts=app.state.allow_test_hosts
    ):
        return "Origin must be loopback"
    if parsed.netloc.lower() != host.lower():
        return "Origin must match Host"
    session = request.cookies.get("specimpact_session")
    csrf = request.headers.get("x-csrf-token")
    with app.state.session_lock:
        _prune_sessions(app)
        if not session or session not in app.state.sessions or csrf != session:
            return "Valid session cookie and CSRF header are required"
        app.state.sessions[session] = time.monotonic()
    return None


def _loopback_host(host: str, *, allow_test_hosts: bool = False) -> bool:
    hostname = urlparse(f"//{host}").hostname
    if not hostname:
        return False
    if allow_test_hosts and hostname == "testserver":
        return True
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _prune_sessions(app: FastAPI) -> None:
    now = time.monotonic()
    cutoff = now - app.state.session_ttl_seconds
    app.state.sessions = {
        token: used_at for token, used_at in app.state.sessions.items() if used_at >= cutoff
    }
    overflow = len(app.state.sessions) - app.state.max_sessions
    if overflow > 0:
        oldest = sorted(app.state.sessions, key=app.state.sessions.get)[:overflow]
        for token in oldest:
            app.state.sessions.pop(token, None)


def _make_session_room(app: FastAPI) -> None:
    if len(app.state.sessions) < app.state.max_sessions:
        return
    oldest = min(app.state.sessions, key=app.state.sessions.get)
    app.state.sessions.pop(oldest, None)
