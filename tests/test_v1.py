from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import ingest_documents
from specimpact.operations import release_validate
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
ENROLLMENT = ROOT / "examples" / "credit_card_enrollment"
RELEASE_CASES = ROOT / "examples" / "evaluation" / "release_cases.yml"
runner = CliRunner()


def ready_store(tmp_path: Path) -> LocalStore:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    return store


def test_three_sample_projects_exist() -> None:
    assert (ROOT / "examples" / "credit_card_enrollment").is_dir()
    assert (ROOT / "examples" / "customer_profile_portal").is_dir()
    assert (ROOT / "examples" / "merchant_risk_console").is_dir()


def test_release_validation(tmp_path: Path) -> None:
    result = release_validate(ready_store(tmp_path), RELEASE_CASES)
    assert result["status"] == "pass"
    assert result["case_count"] == 21
    assert result["category_counts"] == {"golden": 4, "evaluation": 13, "holdout": 4}
    assert result["evaluation_must_review_recall"] >= 0.9
    assert result["checks"]["no_confidence_field"]
    assert result["checks"]["repository_url_configured"]
    assert result["checks"]["security_contact_configured"]
    assert result["unique_expected"] == 20
    assert result["checks"]["unique_expected_at_least_20"]


def test_release_check_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(
        app,
        ["ingest", str(ENROLLMENT / "docs"), "--aliases", str(ENROLLMENT / "aliases.yml")],
    )
    result = runner.invoke(app, ["release-check", str(RELEASE_CASES)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
