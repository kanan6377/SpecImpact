from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import analyze_change, ingest_documents
from specimpact.integrations import (
    configure_backend,
    create_baseline,
    export_obsidian,
    graph_diff,
    import_review_results,
)
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "credit_card_enrollment"
runner = CliRunner()


def analyzed_store(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, SAMPLE / "docs", SAMPLE / "aliases.yml")
    analyze_change(store, SAMPLE / "changes" / "change_credit_limit.md")
    return store


def test_optional_backend_obsidian_and_review_import(tmp_path: Path) -> None:
    store = analyzed_store(tmp_path)
    configure_backend(store, "neo4j", "bolt://localhost:7687")
    config = yaml.safe_load((store.root / "config.yml").read_text(encoding="utf-8"))
    assert config["backend"] == "neo4j"
    dashboard = export_obsidian(store, tmp_path / "vault")
    assert dashboard.exists()
    assert (tmp_path / "vault" / "SpecImpact" / "Artifacts").is_dir()
    assert (tmp_path / "vault" / "SpecImpact" / "Evidence").is_dir()
    assert list((tmp_path / "vault" / "SpecImpact" / "Canvases").glob("*.canvas"))
    count = import_review_results(store, SAMPLE / "reviews" / "change_credit_limit.review.json")
    assert count == 2


def test_graph_diff(tmp_path: Path) -> None:
    store = analyzed_store(tmp_path)
    create_baseline(store, "before")
    relations = store.root / "relations.jsonl"
    lines = relations.read_text(encoding="utf-8").splitlines()
    relations.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    assert graph_diff(store, "before")["removed"]


def test_v05_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ingest", str(SAMPLE / "docs"), "--aliases", str(SAMPLE / "aliases.yml")])
    runner.invoke(app, ["analyze", str(SAMPLE / "changes" / "change_credit_limit.md")])
    backend = runner.invoke(app, ["backend", "set", "neo4j", "--uri", "bolt://localhost"])
    assert backend.exit_code == 0
    assert runner.invoke(app, ["export-obsidian", str(tmp_path / "vault")]).exit_code == 0
    onboard_vault = tmp_path / "onboard-vault"
    onboard = runner.invoke(
        app,
        [
            "onboard",
            str(SAMPLE / "docs"),
            "--no-llm",
            "--aliases",
            str(SAMPLE / "aliases.yml"),
            "--obsidian-vault",
            str(onboard_vault),
        ],
    )
    assert onboard.exit_code == 0
    assert (onboard_vault / "SpecImpact" / "Dashboard.md").is_file()
    review = SAMPLE / "reviews" / "change_credit_limit.review.json"
    assert runner.invoke(app, ["review", "import", str(review)]).exit_code == 0
    assert runner.invoke(app, ["baseline", "create", "before"]).exit_code == 0
    assert runner.invoke(app, ["graph", "diff", "before"]).exit_code == 0
