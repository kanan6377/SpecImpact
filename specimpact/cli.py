from __future__ import annotations

import json
import threading
import webbrowser
from pathlib import Path

import typer

from specimpact.core import (
    analyze_change,
    explain_why,
    ingest_documents,
    latest_run_dir,
)
from specimpact.embeddings import rebuild_embeddings
from specimpact.graphrag import configure_llm, disable_llm, llm_status
from specimpact.inspection import (
    decide_alias,
    inspect_artifact,
    inspect_evidence,
    inspect_graph,
    list_aliases,
    list_relations,
    remove_alias,
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
from specimpact.store import LocalStore
from specimpact.structured_loaders import ingest_ddl, ingest_openapi
from specimpact.tabular_loaders import ingest_csv, ingest_excel

app = typer.Typer(help="Evidence-first software design change impact review CLI.")
aliases_app = typer.Typer(help="Review manual and suggested aliases.")
inspect_app = typer.Typer(help="Inspect local graph state.")
relations_app = typer.Typer(help="Review extracted relation status.")
backend_app = typer.Typer(help="Configure optional graph backend.")
baseline_app = typer.Typer(help="Create graph baselines.")
graph_app = typer.Typer(help="Compare graph state.")
review_app = typer.Typer(help="Import reviewer decisions.")
llm_app = typer.Typer(help="Configure optional LLM extraction and reranking.")
embeddings_app = typer.Typer(help="Build and inspect local-first semantic embeddings.")
app.add_typer(aliases_app, name="aliases")
app.add_typer(inspect_app, name="inspect")
app.add_typer(relations_app, name="relations")
app.add_typer(backend_app, name="backend")
app.add_typer(baseline_app, name="baseline")
app.add_typer(graph_app, name="graph")
app.add_typer(review_app, name="review")
app.add_typer(llm_app, name="llm")
app.add_typer(embeddings_app, name="embeddings")


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
def ingest(
    docs_dir: Path,
    aliases: Path | None = typer.Option(None, help="Manual aliases.yml file."),
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Temporarily disable LLM calls."),
) -> None:
    """Ingest Markdown and text design documents."""
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
def ingest_excel_command(path: Path) -> None:
    """Ingest simple header-row Excel sheets."""
    typer.echo(f"Ingested {len(_call(ingest_excel, LocalStore(), path))} Excel sheets.")


@app.command()
def analyze(
    change_request: Path,
    yes: bool = typer.Option(False, "--yes", help="Approve external transmission."),
    no_llm: bool = typer.Option(False, "--no-llm", help="Temporarily disable LLM calls."),
) -> None:
    """Analyze a change request and write a new review run."""
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
def show_report(format: str = typer.Option("markdown", help="markdown or json")) -> None:
    """Print the latest report."""
    run_dir = _call(latest_run_dir, LocalStore())
    if format == "markdown":
        typer.echo((run_dir / "report.md").read_text(encoding="utf-8"))
    elif format == "json":
        data = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        raise typer.BadParameter("format must be markdown or json")


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
def aliases_suggest() -> None:
    """Generate inspectable local alias suggestions."""
    typer.echo(f"Created {_call(suggest_aliases, LocalStore())} alias suggestions.")


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
def aliases_reject(target_id: str, alias: str) -> None:
    """Reject an alias suggestion."""
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
def export_obsidian_command(output_dir: Path) -> None:
    """Export the latest Markdown report for Obsidian."""
    typer.echo(f"Exported {_call(export_obsidian, LocalStore(), output_dir)}")


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


@llm_app.command("configure")
def llm_configure(
    provider: str = typer.Option(..., help="openai, ollama, codex, or fake"),
    model: str = typer.Option(..., help="Provider model name."),
    base_url: str | None = typer.Option(None, help="Required for Ollama."),
) -> None:
    """Enable an optional LLM provider."""
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


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (OSError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
