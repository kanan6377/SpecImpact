from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import analyze_change, ingest_documents
from specimpact.impact_management.decision_store import ImpactDecision
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
    store.write(
        "impact_decisions",
        [
            ImpactDecision(
                impact_id="impact.change_credit_limit.api.card_application.submit",
                change_id="change_credit_limit",
                candidate_node_id="api.card_application.submit",
                status="accepted",
                reason="snapshot review",
            )
        ],
    )
    dashboard = export_obsidian(store, tmp_path / "vault")
    assert dashboard.exists()
    vault_root = tmp_path / "vault" / "SpecImpact"
    assert (vault_root / "Artifacts").is_dir()
    assert (vault_root / "Evidence").is_dir()
    assert (vault_root / "Impacts").is_dir()
    dashboard_text = dashboard.read_text(encoding="utf-8")
    assert "# SpecImpact Dashboard" in dashboard_text
    assert 'TABLE status, review_priority, impact_type FROM "SpecImpact/Impacts"' in dashboard_text
    artifact_notes = list((vault_root / "Artifacts").glob("*.md"))
    evidence_notes = list((vault_root / "Evidence").glob("*.md"))
    impact_notes = list((vault_root / "Impacts").glob("*.md"))
    canvas_files = list((vault_root / "Canvases").glob("*.canvas"))
    assert artifact_notes
    assert evidence_notes
    assert impact_notes
    assert canvas_files
    assert any("artifact_type:" in item.read_text(encoding="utf-8") for item in artifact_notes)
    assert any("source_file:" in item.read_text(encoding="utf-8") for item in evidence_notes)
    impact_text = impact_notes[0].read_text(encoding="utf-8")
    assert "type: impact_decision" in impact_text
    assert "status: \"accepted\"" in impact_text
    canvas = json.loads(canvas_files[0].read_text(encoding="utf-8"))
    assert canvas["nodes"]
    assert canvas["edges"]
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
