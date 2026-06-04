from __future__ import annotations

from pathlib import Path

import yaml
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import ingest_documents
from specimpact.inspection import remove_alias, set_relation_status
from specimpact.models import Relation
from specimpact.operations import evaluate_dataset
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "credit_card_enrollment"
runner = CliRunner()


def ready_store(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, SAMPLE / "docs", SAMPLE / "aliases.yml")
    return store


def test_relation_status_and_alias_edit(tmp_path: Path) -> None:
    store = ready_store(tmp_path)
    relation_id = next(
        item.relation_id
        for item in store.read("relations", Relation)
        if item.source_id == "api.card_application.submit"
        and item.target_id == "entity.application.requested_credit_limit"
    )
    set_relation_status(store, relation_id, "confirmed")
    relation = next(
        item for item in store.read("relations", Relation) if item.relation_id == relation_id
    )
    assert relation.status == "confirmed"
    remove_alias(store, "api.card_application.submit", "入会申込API")
    aliases = yaml.safe_load((store.root / "aliases.yml").read_text(encoding="utf-8"))
    assert "入会申込API" not in aliases["aliases"]["api.card_application.submit"]["aliases"]


def test_dataset_evaluation(tmp_path: Path) -> None:
    store = ready_store(tmp_path)
    result = evaluate_dataset(store, SAMPLE / "evaluation" / "cases.yml")
    assert result["case_count"] == 3
    assert all(case["must_review_recall"] == 1.0 for case in result["cases"])


def test_v02_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["ingest", str(SAMPLE / "docs"), "--aliases", str(SAMPLE / "aliases.yml")])
    relation_id = next(
        item.relation_id
        for item in LocalStore().read("relations", Relation)
        if item.source_id == "api.card_application.submit"
        and item.target_id == "entity.application.requested_credit_limit"
    )
    assert runner.invoke(app, ["relations", "list"]).exit_code == 0
    assert runner.invoke(app, ["relations", "set-status", relation_id, "confirmed"]).exit_code == 0
    added = runner.invoke(app, ["aliases", "add", "api.card_application.submit", "submit-v2"])
    removed = runner.invoke(app, ["aliases", "remove", "api.card_application.submit", "submit-v2"])
    assert added.exit_code == 0
    assert removed.exit_code == 0
    result = runner.invoke(app, ["eval", "--dataset", str(SAMPLE / "evaluation" / "cases.yml")])
    assert result.exit_code == 0
    assert '"case_count": 3' in result.stdout
