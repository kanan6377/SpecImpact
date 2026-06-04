from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import analyze_change, ingest_documents
from specimpact.inspection import (
    decide_alias,
    inspect_artifact,
    inspect_evidence,
    inspect_graph,
    suggest_aliases,
)
from specimpact.models import Evidence, Relation
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "credit_card_enrollment"
runner = CliRunner()


def ready_store(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, SAMPLE / "docs", SAMPLE / "aliases.yml")
    return store


def test_additional_change_cases(tmp_path: Path) -> None:
    store = ready_store(tmp_path)
    income = analyze_change(store, SAMPLE / "changes" / "change_income_review_threshold.md")
    address = analyze_change(store, SAMPLE / "changes" / "change_address_required_rule.md")
    assert income.change.changed_entity_ids == [
        "entity.application.annual_income",
        "entity.application.requested_credit_limit",
    ]
    assert address.change.changed_entity_ids == ["entity.application.address"]
    assert any(item.artifact_id == "external_if.identity_verification" for item in address.impacts)


def test_alias_workflow_and_inspection(tmp_path: Path) -> None:
    store = ready_store(tmp_path)
    assert suggest_aliases(store) > 0
    decide_alias(store, "api.card_application.submit", "submit-api", "approved")
    assert "submit-api" in (store.root / "aliases.yml").read_text(encoding="utf-8")
    decide_alias(store, "api.card_application.submit", "unused-api", "rejected")
    rows = (store.root / "alias_suggestions.jsonl").read_text(encoding="utf-8")
    assert '"status": "rejected"' in rows
    assert "REQUEST_FIELD" in inspect_graph(store)
    assert "quote" in inspect_evidence(store)
    assert "api.card_application.submit" in inspect_artifact(store, "カード入会申込API")
    relations = store.read("relations", Relation)
    evidence = store.read("evidence", Evidence)
    assert len({item.relation_id for item in relations}) == len(relations)
    assert len({item.evidence_id for item in evidence}) == len(evidence)


def test_alpha2_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ingest", str(SAMPLE / "docs"), "--aliases", str(SAMPLE / "aliases.yml")])
    assert runner.invoke(app, ["aliases", "suggest"]).exit_code == 0
    assert runner.invoke(app, ["aliases", "list"]).exit_code == 0
    approved = runner.invoke(
        app, ["aliases", "approve", "api.card_application.submit", "submit-api"]
    )
    rejected = runner.invoke(app, ["aliases", "reject", "api.card_application.submit", "bad-api"])
    assert approved.exit_code == 0
    assert rejected.exit_code == 0
    graph = runner.invoke(app, ["inspect", "graph"])
    assert graph.exit_code == 0 and "REQUEST_FIELD" in graph.stdout
    assert runner.invoke(app, ["inspect", "evidence"]).exit_code == 0
    artifact = runner.invoke(app, ["inspect", "artifact", "カード入会申込API"])
    assert artifact.exit_code == 0
    assert json.loads(artifact.stdout)[0]["artifact_id"] == "api.card_application.submit"
