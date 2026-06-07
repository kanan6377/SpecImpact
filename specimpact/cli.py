from __future__ import annotations

import hashlib
import json
import threading
import webbrowser
from pathlib import Path
from typing import Any

import typer

from specimpact.core import (
    analyze_change,
    explain_why,
    ingest_documents,
    latest_run_dir,
)
from specimpact.dirty_excel.ingestion import (
    decide_graph_proposal,
    ingest_dirty_excel,
    inspect_dirty_excel,
    list_graph_proposals,
)
from specimpact.embeddings import rebuild_embeddings
from specimpact.graphrag import configure_llm, disable_llm, llm_status
from specimpact.impact_management.change_atoms import (
    list_changes,
    parse_change_atoms,
    show_change,
)
from specimpact.impact_management.decision_store import list_impacts, set_impact_status
from specimpact.impact_management.review_session import analyze_change_llm_first
from specimpact.inspection import (
    confirm_alias_candidate,
    decide_alias,
    inspect_artifact,
    inspect_evidence,
    inspect_graph,
    list_aliases,
    list_relations,
    reject_alias_candidate,
    remove_alias,
    review_alias_candidates,
    set_relation_status,
    suggest_aliases,
)
from specimpact.integrations import (
    configure_backend,
    create_baseline,
    export_obsidian,
    graph_diff,
    import_review_results,
)
from specimpact.operations import (
    evaluate_dataset,
    evaluate_latest,
    explain_why_not,
    privacy_doctor,
    project_status,
    release_validate,
)
from specimpact.reports import export_report_excel
from specimpact.store import LocalStore
from specimpact.structured_loaders import ingest_ddl, ingest_openapi
from specimpact.tabular_loaders import ingest_csv, ingest_excel, inspect_excel_folder

app = typer.Typer(help="LLM-first, evidence-verified design impact management CLI.")
aliases_app = typer.Typer(help="Review manual and suggested aliases.")
inspect_app = typer.Typer(help="Inspect local graph state.")
relations_app = typer.Typer(help="Review extracted relation status.")
backend_app = typer.Typer(help="Configure graph backend.")
baseline_app = typer.Typer(help="Create graph baselines.")
graph_app = typer.Typer(help="Compare graph state.")
graph_proposals_app = typer.Typer(help="Review LLM graph proposals.")
review_app = typer.Typer(help="Import reviewer decisions.")
llm_app = typer.Typer(help="Configure the standard LLM provider.")
embeddings_app = typer.Typer(help="Build and inspect local-first semantic embeddings.")
excel_app = typer.Typer(help="Inspect and lint Excel design workbooks.")
change_app = typer.Typer(help="Parse and inspect structured change atoms.")
changes_app = typer.Typer(help="List parsed changes.")
impacts_app = typer.Typer(help="Manage impact review decisions.")
app.add_typer(aliases_app, name="aliases")
app.add_typer(inspect_app, name="inspect")
app.add_typer(relations_app, name="relations")
app.add_typer(backend_app, name="backend")
app.add_typer(baseline_app, name="baseline")
app.add_typer(graph_app, name="graph")
graph_app.add_typer(graph_proposals_app, name="proposals")
app.add_typer(review_app, name="review")
app.add_typer(llm_app, name="llm")
app.add_typer(embeddings_app, name="embeddings")
app.add_typer(excel_app, name="excel")
app.add_typer(change_app, name="change")
app.add_typer(changes_app, name="changes")
app.add_typer(impacts_app, name="impacts")


@app.command()
def gui(
    port: int = typer.Option(8765, min=1, max=65535, help="Local HTTP port."),
    project: Path | None = typer.Option(None, help="Register and open a project directory."),
    no_open_browser: bool = typer.Option(False, "--no-open-browser", help="Do not open a browser."),
) -> None:
    """Start the optional localhost-only web UI."""
    try:
        import uvicorn

        from specimpact.webui import create_app
    except ImportError as error:
        raise typer.BadParameter('GUI requires pip install -e ".[gui]"') from error
    application = create_app()
    project_id = None
    if project:
        try:
            registered = application.state.registry.add(project)
        except ValueError as error:
            raise typer.BadParameter(str(error)) from error
        project_id = registered.project_id
    url = f"http://127.0.0.1:{port}/"
    if project_id:
        url += f"?project_id={project_id}"
    if not no_open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    typer.echo(f"Starting SpecImpact GUI at {url}")
    uvicorn.run(application, host="127.0.0.1", port=port)


@app.command()
def init() -> None:
    """Initialize local SpecImpact state."""
    LocalStore().init()
    typer.echo("Initialized .specimpact/")


@app.command()
def onboard(
    path: Path,
    mode: str = typer.Option("auto", help="auto, markdown, or dirty-excel."),
    provider: str = typer.Option("codex", help="codex, openai, ollama, fake, or none."),
    model: str = typer.Option("default", help="LLM model name."),
    base_url: str | None = typer.Option(None, help="Required for Ollama."),
    aliases: Path | None = typer.Option(None, help="Manual aliases.yml file."),
    obsidian_vault: Path | None = typer.Option(
        None,
        "--obsidian-vault",
        help="Export a review vault after onboarding.",
    ),
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Use local-only fallback."),
) -> None:
    """Run the standard LLM-first project onboarding flow."""
    store = LocalStore()
    store.init()
    if no_llm or provider == "none":
        no_llm = True
        typer.echo("LLM provider skipped; using local-only fallback.")
    else:
        _call(configure_llm, store, provider, model, base_url)
        typer.echo(f"Configured {provider} LLM provider with model {model}.")
    detected_mode = _detect_onboard_mode(path) if mode == "auto" else mode
    if detected_mode == "dirty-excel":
        summary = _call(
            ingest_dirty_excel,
            store,
            path,
            aliases,
            use_llm=not no_llm,
            yes=yes,
            confirm=typer.confirm,
        )
        typer.echo(
            "Onboarded dirty Excel: "
            f"{summary.workbooks} workbooks, {summary.regions} regions, "
            f"{summary.proposals} graph proposals."
        )
    elif detected_mode == "markdown":
        count = _call(
            ingest_documents,
            store,
            path,
            aliases,
            yes=yes,
            no_llm=no_llm,
            confirm=typer.confirm,
        )
        typer.echo(f"Onboarded {count} documents.")
    else:
        raise typer.BadParameter("mode must be auto, markdown, or dirty-excel")
    if obsidian_vault:
        target = _call(export_obsidian, store, obsidian_vault)
        typer.echo(f"Exported Obsidian review vault: {target}")


@app.command()
def ingest(
    docs_dir: Path,
    mode: str = typer.Option("markdown", help="markdown or dirty-excel."),
    aliases: Path | None = typer.Option(None, help="Manual aliases.yml file."),
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Temporarily disable LLM calls."),
) -> None:
    """Ingest Markdown/text documents or dirty Excel workbooks."""
    if mode == "dirty-excel":
        summary = _call(
            ingest_dirty_excel,
            LocalStore(),
            docs_dir,
            aliases,
            use_llm=not no_llm,
            yes=yes,
            confirm=typer.confirm,
        )
        typer.echo(f"Ingested {summary.workbooks} dirty Excel workbooks.")
        return
    if mode != "markdown":
        raise typer.BadParameter("mode must be markdown or dirty-excel")
    count = _call(
        ingest_documents,
        LocalStore(),
        docs_dir,
        aliases,
        yes=yes,
        no_llm=no_llm,
        confirm=typer.confirm,
    )
    typer.echo(f"Ingested {count} documents.")


@app.command("ingest-openapi")
def ingest_openapi_command(path: Path) -> None:
    """Ingest an OpenAPI YAML or JSON document."""
    typer.echo(f"Ingested {len(_call(ingest_openapi, LocalStore(), path))} OpenAPI operations.")


@app.command("ingest-ddl")
def ingest_ddl_command(path: Path) -> None:
    """Ingest SQL DDL tables and columns."""
    typer.echo(f"Ingested {len(_call(ingest_ddl, LocalStore(), path))} DDL tables.")


@app.command("ingest-csv")
def ingest_csv_command(path: Path) -> None:
    """Ingest a header-row CSV table."""
    typer.echo(f"Ingested {len(_call(ingest_csv, LocalStore(), path))} CSV tables.")


@app.command("ingest-excel")
def ingest_excel_command(
    path: Path,
    profile: str | None = typer.Option(None, help="Excel profile, e.g. sier."),
    aliases: Path | None = typer.Option(None, help="Manual aliases.yml file."),
) -> None:
    """Ingest Excel workbooks or a directory of SIer Excel design documents."""
    typer.echo(
        f"Ingested {len(_call(ingest_excel, LocalStore(), path, aliases, profile))} Excel sheets."
    )


@app.command("ingest-dirty-excel")
def ingest_dirty_excel_command(
    path: Path,
    llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Use configured LLM for region extraction.",
    ),
    aliases: Path | None = typer.Option(None, help="Manual aliases.yml file."),
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
) -> None:
    """Ingest messy SIer Excel workbooks with cell-level evidence."""
    summary = _call(
        ingest_dirty_excel,
        LocalStore(),
        path,
        aliases,
        use_llm=llm,
        yes=yes,
        confirm=typer.confirm,
    )
    typer.echo(
        "Ingested "
        f"{summary.workbooks} workbooks, {summary.regions} regions, "
        f"{summary.proposals} graph proposals."
    )


@app.command()
def analyze(
    change_request: Path,
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Temporarily disable LLM calls."),
    llm_first: bool = typer.Option(
        False,
        "--llm-first",
        help="Use standard Change Atom impact flow.",
    ),
) -> None:
    """Analyze a change request and write a new review run."""
    if llm_first:
        report = _call(
            analyze_change_llm_first,
            LocalStore(),
            change_request,
            yes=yes,
            no_llm=no_llm,
            confirm=typer.confirm,
        )
        typer.echo(f"Created run {report.run_id} with {len(report.impacts)} candidates.")
        return
    report = _call(
        analyze_change,
        LocalStore(),
        change_request,
        yes=yes,
        no_llm=no_llm,
        confirm=typer.confirm,
    )
    typer.echo(f"Created run {report.run_id} with {len(report.impacts)} candidates.")


@app.command("report")
def show_report(format: str = typer.Option("markdown", help="markdown, json, or excel")) -> None:
    """Print the latest report."""
    run_dir = _call(latest_run_dir, LocalStore())
    if format == "markdown":
        typer.echo((run_dir / "report.md").read_text(encoding="utf-8"))
    elif format == "json":
        data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    elif format == "excel":
        typer.echo(str(_call(export_report_excel, LocalStore())))
    else:
        raise typer.BadParameter("format must be markdown, json, or excel")


@app.command()
def why(name: str) -> None:
    """Explain why an artifact appears in the latest report."""
    typer.echo(_call(explain_why, LocalStore(), name))


@app.command("why-not")
def why_not(name: str) -> None:
    """Explain trace-backed candidate exclusion."""
    typer.echo(_call(explain_why_not, LocalStore(), name))


@app.command()
def status() -> None:
    """Show local state and latest run."""
    typer.echo(_call(project_status, LocalStore()))


@app.command()
def doctor(
    privacy: bool = typer.Option(False, "--privacy", help="Check local privacy defaults."),
) -> None:
    """Check configuration."""
    if privacy:
        typer.echo(_call(privacy_doctor, LocalStore()))
    else:
        typer.echo("Use --privacy to inspect local privacy defaults.")


@app.command("eval")
def evaluate(
    expected: Path = typer.Option(
        Path("examples/credit_card_enrollment/expected/change_credit_limit.expected.json"),
        help="Expected result JSON.",
    ),
    dataset: Path | None = typer.Option(None, help="Evaluation dataset manifest."),
) -> None:
    """Evaluate the latest report against an expected result."""
    store = LocalStore()
    metrics = (
        _call(evaluate_dataset, store, dataset)
        if dataset
        else _call(evaluate_latest, store, expected)
    )
    typer.echo(json.dumps(metrics, indent=2))


@app.command("release-check")
def release_check(dataset: Path) -> None:
    """Run the v1 release evaluation gates."""
    result = _call(release_validate, LocalStore(), dataset)
    typer.echo(json.dumps(result, indent=2))
    if result["status"] != "pass":
        raise typer.Exit(code=1)


@aliases_app.command("suggest")
def aliases_suggest(
    llm: bool = typer.Option(True, "--llm/--no-llm", help="Use v2 alias inference."),
) -> None:
    """Generate inspectable local alias suggestions."""
    typer.echo(f"Created {_call(suggest_aliases, LocalStore(), use_llm=llm)} alias suggestions.")


@aliases_app.command("review")
def aliases_review() -> None:
    """List v2 alias candidates."""
    typer.echo(_call(review_alias_candidates, LocalStore()))


@aliases_app.command("confirm")
def aliases_confirm(candidate_id: str) -> None:
    """Confirm a v2 alias candidate."""
    candidate = _call(confirm_alias_candidate, LocalStore(), candidate_id)
    typer.echo(f"Confirmed {candidate.candidate_id}.")


@aliases_app.command("reject-candidate")
def aliases_reject_candidate(candidate_id: str) -> None:
    """Reject a v2 alias candidate."""
    candidate = _call(reject_alias_candidate, LocalStore(), candidate_id)
    typer.echo(f"Rejected {candidate.candidate_id}.")


@aliases_app.command("list")
def aliases_list() -> None:
    """List aliases and suggestions."""
    typer.echo(_call(list_aliases, LocalStore()))


@aliases_app.command("approve")
def aliases_approve(target_id: str, alias: str) -> None:
    """Approve an alias suggestion."""
    _call(decide_alias, LocalStore(), target_id, alias, "approved")
    typer.echo(f"Approved {alias} for {target_id}.")


@aliases_app.command("reject")
def aliases_reject(target_id: str, alias: str | None = typer.Argument(None)) -> None:
    """Reject an alias suggestion or v2 alias candidate."""
    if alias is None:
        candidate = _call(reject_alias_candidate, LocalStore(), target_id)
        typer.echo(f"Rejected {candidate.candidate_id}.")
        return
    _call(decide_alias, LocalStore(), target_id, alias, "rejected")
    typer.echo(f"Rejected {alias} for {target_id}.")


@aliases_app.command("add")
def aliases_add(target_id: str, alias: str) -> None:
    """Add a reviewed alias."""
    _call(decide_alias, LocalStore(), target_id, alias, "approved")
    typer.echo(f"Added {alias} for {target_id}.")


@aliases_app.command("remove")
def aliases_remove(target_id: str, alias: str) -> None:
    """Remove an alias."""
    _call(remove_alias, LocalStore(), target_id, alias)
    typer.echo(f"Removed {alias} from {target_id}.")


@inspect_app.command("graph")
def graph_inspect() -> None:
    """Inspect graph relations."""
    typer.echo(_call(inspect_graph, LocalStore()))


@inspect_app.command("evidence")
def evidence_inspect(evidence_id: str | None = typer.Argument(None)) -> None:
    """Inspect evidence records."""
    typer.echo(_call(inspect_evidence, LocalStore(), evidence_id))


@inspect_app.command("artifact")
def artifact_inspect(name: str) -> None:
    """Inspect an artifact by ID, display name, or alias."""
    typer.echo(_call(inspect_artifact, LocalStore(), name))


@relations_app.command("list")
def relations_list() -> None:
    """List relations and review state."""
    typer.echo(_call(list_relations, LocalStore()))


@relations_app.command("set-status")
def relations_set_status(relation_id: str, status: str) -> None:
    """Set confirmed, unconfirmed, or rejected relation state."""
    try:
        set_relation_status(LocalStore(), relation_id, status)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Set {relation_id} to {status}.")


@backend_app.command("set")
def backend_set(backend: str, uri: str | None = typer.Option(None)) -> None:
    """Select local or optional Neo4j backend configuration."""
    try:
        configure_backend(LocalStore(), backend, uri)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Configured {backend} backend.")


@app.command("export-obsidian")
def export_obsidian_command(
    output_dir: Path,
    report_only: bool = typer.Option(
        False,
        "--report-only",
        help="Only copy the latest Markdown report.",
    ),
) -> None:
    """Export an Obsidian review vault with graph notes and impact canvas."""
    typer.echo(
        f"Exported {_call(export_obsidian, LocalStore(), output_dir, report_only=report_only)}"
    )


@review_app.command("import")
def review_import(path: Path) -> None:
    """Import review decisions from JSON."""
    typer.echo(f"Imported {_call(import_review_results, LocalStore(), path)} review results.")


@baseline_app.command("create")
def baseline_create(name: str) -> None:
    """Create a relation baseline."""
    typer.echo(f"Created {_call(create_baseline, LocalStore(), name)}")


@graph_app.command("diff")
def graph_diff_command(name: str) -> None:
    """Compare current relations with a baseline."""
    typer.echo(json.dumps(_call(graph_diff, LocalStore(), name), indent=2))


@graph_proposals_app.command("list")
def graph_proposals_list() -> None:
    """List graph extraction proposals."""
    typer.echo(_call(list_graph_proposals, LocalStore()))


@graph_proposals_app.command("accept")
def graph_proposals_accept(proposal_id: str) -> None:
    """Accept a graph extraction proposal."""
    proposal = _call(decide_graph_proposal, LocalStore(), proposal_id, "accepted")
    typer.echo(f"Accepted {proposal.proposal_id}.")


@graph_proposals_app.command("reject")
def graph_proposals_reject(proposal_id: str) -> None:
    """Reject a graph extraction proposal."""
    proposal = _call(decide_graph_proposal, LocalStore(), proposal_id, "rejected")
    typer.echo(f"Rejected {proposal.proposal_id}.")


@llm_app.command("configure")
def llm_configure(
    provider: str = typer.Option(..., help="openai, ollama, codex, or fake"),
    model: str = typer.Option(..., help="Provider model name."),
    base_url: str | None = typer.Option(None, help="Required for Ollama."),
) -> None:
    """Enable the standard LLM provider."""
    _call(configure_llm, LocalStore(), provider, model, base_url)
    typer.echo(f"Configured {provider} LLM provider with model {model}.")


@llm_app.command("disable")
def llm_disable() -> None:
    """Disable LLM calls without removing local graph data."""
    _call(disable_llm, LocalStore())
    typer.echo("Disabled LLM provider.")


@llm_app.command("status")
def llm_show_status() -> None:
    """Show LLM provider status without secrets."""
    typer.echo(json.dumps(_call(llm_status, LocalStore()), indent=2))


@embeddings_app.command("rebuild")
def embeddings_rebuild(
    provider: str = typer.Option("local", help="local or openai"),
    model: str | None = typer.Option(None, help="Embedding model name."),
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
) -> None:
    """Incrementally rebuild semantic chunk embeddings."""
    count = _call(
        rebuild_embeddings,
        LocalStore(),
        provider=provider,
        model=model,
        yes=yes,
        confirm=typer.confirm,
    )
    typer.echo(f"Rebuilt {count} embeddings.")


@excel_app.command("inspect")
def excel_inspect(path: Path) -> None:
    """Show an Excel Health Check for a workbook or workbook directory."""
    typer.echo(_render_health_check(_call(inspect_excel_folder, path)))


@excel_app.command("classify")
def excel_classify(path: Path) -> None:
    """Inspect dirty Excel sheet and region classification."""
    typer.echo(json.dumps(_call(inspect_dirty_excel, path), ensure_ascii=False, indent=2))


@excel_app.command("lint")
def excel_lint(path: Path) -> None:
    """Return non-zero when Excel Health Check warnings are present."""
    health = _call(inspect_excel_folder, path)
    typer.echo(json.dumps(health, ensure_ascii=False, indent=2))
    if health.get("warnings"):
        raise typer.Exit(code=1)


@change_app.command("parse")
def change_parse(path: Path) -> None:
    """Parse a change request into Change Atoms."""
    extraction = _call(parse_change_atoms, LocalStore(), path)
    typer.echo(json.dumps(extraction.model_dump(), ensure_ascii=False, indent=2))


@change_app.command("analyze")
def change_analyze(change: str) -> None:
    """Analyze a change request path or natural-language text with the standard flow."""
    store = LocalStore()
    store.init()
    path = Path(change)
    if path.exists():
        change_path = path
    else:
        digest = hashlib.sha1(change.encode("utf-8")).hexdigest()[:12]
        change_path = store.root / "changes" / f"change-{digest}.md"
        store.write_text(change_path, f"# Change Request\n\n{change.strip()}\n")
    report = _call(
        analyze_change_llm_first,
        store,
        change_path,
        yes=False,
        no_llm=False,
        confirm=typer.confirm,
    )
    typer.echo(f"Created run {report.run_id} with {len(report.impacts)} candidates.")


@changes_app.command("list")
def changes_list() -> None:
    """List parsed changes."""
    typer.echo(_call(list_changes, LocalStore()))


@changes_app.command("show")
def changes_show(change_id: str) -> None:
    """Show parsed Change Atoms for a change."""
    typer.echo(_call(show_change, LocalStore(), change_id))


@impacts_app.command("list")
def impacts_list(
    change: str | None = typer.Option(None, "--change", help="Filter by change ID."),
) -> None:
    """List persisted impact review decisions."""
    typer.echo(_call(list_impacts, LocalStore(), change))


@impacts_app.command("set-status")
def impacts_set_status(
    impact_id: str,
    status: str,
    reason: str = typer.Option("", help="Reviewer reason."),
) -> None:
    """Set impact review status."""
    decision = _call(set_impact_status, LocalStore(), impact_id, status, reason)
    typer.echo(f"Set {decision.impact_id} to {decision.status}.")


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error


def _render_health_check(health: dict[str, Any]) -> str:
    warning_lines = [
        f"- merged cells: {health.get('merged_cells', 0)}",
        f"- hidden sheets: {health.get('hidden_sheets', 0)}",
        f"- revision history sheets: {len(health.get('revision_history_sheets', []))}",
        f"- duplicate item names: {len(health.get('duplicate_field_names', []))}",
        f"- alias candidates: {len(health.get('alias_candidates', []))}",
    ]
    extra = [f"- {item}" for item in health.get("warnings", [])]
    return "\n".join(
        [
            "Excel Health Check",
            "",
            f"Workbooks: {health.get('workbooks', 0)}",
            f"Sheets: {health.get('sheets', 0)}",
            f"Detected artifacts: {health.get('detected_artifacts', 0)}",
            f"Possible relations: {health.get('possible_relations', 0)}",
            "",
            "Warnings:",
            *warning_lines,
            *extra,
        ]
    )


def _detect_onboard_mode(path: Path) -> str:
    if path.is_file() and path.suffix.lower() == ".xlsx":
        return "dirty-excel"
    if path.is_dir() and any(item.suffix.lower() == ".xlsx" for item in path.iterdir()):
        return "dirty-excel"
    return "markdown"
