from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import analyze_change, ingest_documents, latest_run_dir
from specimpact.operations import evaluate_latest, explain_why_not, privacy_doctor, project_status
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "credit_card_enrollment"
runner = CliRunner()


def analyzed_store(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, SAMPLE / "docs", SAMPLE / "aliases.yml")
    analyze_change(store, SAMPLE / "changes" / "change_credit_limit.md")
    return store


def test_trace_backed_why_not(tmp_path: Path) -> None:
    store = analyzed_store(tmp_path)
    trace = latest_run_dir(store) / "trace.jsonl"
    assert trace.exists()
    output = explain_why_not(store, "本人確認サービス")
    assert "external_if.identity_verification" in output
    assert "Candidate state: excluded" in output


def test_status_privacy_and_eval(tmp_path: Path) -> None:
    store = analyzed_store(tmp_path)
    assert json.loads(project_status(store))["backend"] == "local"
    assert "External LLM configured: no" in privacy_doctor(store)
    metrics = evaluate_latest(store, SAMPLE / "expected" / "change_credit_limit.expected.json")
    assert metrics["must_review_recall"] == 1.0
    assert metrics["should_review_recall"] == 1.0
    assert metrics["evidence_coverage"] == 1.0


def test_alpha3_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ingest", str(SAMPLE / "docs"), "--aliases", str(SAMPLE / "aliases.yml")])
    runner.invoke(app, ["analyze", str(SAMPLE / "changes" / "change_credit_limit.md")])
    assert runner.invoke(app, ["why-not", "本人確認サービス"]).exit_code == 0
    assert runner.invoke(app, ["status"]).exit_code == 0
    assert runner.invoke(app, ["doctor", "--privacy"]).exit_code == 0
    result = runner.invoke(
        app,
        ["eval", "--expected", str(SAMPLE / "expected" / "change_credit_limit.expected.json")],
    )
    assert result.exit_code == 0
    assert '"must_review_recall": 1.0' in result.stdout
