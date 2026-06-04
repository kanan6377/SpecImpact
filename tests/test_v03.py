from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.models import Artifact
from specimpact.store import LocalStore
from specimpact.structured_loaders import ingest_ddl, ingest_openapi

ROOT = Path(__file__).parents[1]
STRUCTURED = ROOT / "examples" / "credit_card_enrollment" / "structured"
runner = CliRunner()


def test_openapi_yaml_loader(tmp_path: Path) -> None:
    records = ingest_openapi(
        LocalStore(tmp_path / ".specimpact"), STRUCTURED / "card_application.openapi.yml"
    )
    assert records[0]["endpoint"] == "/api/card-applications"
    assert records[0]["request_fields"] == ["applicantName", "requestedCreditLimit"]
    assert records[0]["response_fields"] == ["applicationId", "screeningStatus"]
    assert records[0]["schemas"] == ["CardApplication"]


def test_ddl_loader(tmp_path: Path) -> None:
    records = ingest_ddl(LocalStore(tmp_path / ".specimpact"), STRUCTURED / "schema.sql")
    assert [record["display_name"] for record in records] == [
        "CARD_APPLICATION",
        "SCREENING_RESULT",
    ]
    assert records[0]["columns"][2]["name"] == "requested_credit_limit"
    assert records[1]["constraints"]


def test_v03_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    openapi = runner.invoke(
        app, ["ingest-openapi", str(STRUCTURED / "card_application.openapi.yml")]
    )
    assert openapi.exit_code == 0
    assert runner.invoke(app, ["ingest-ddl", str(STRUCTURED / "schema.sql")]).exit_code == 0
    artifacts = LocalStore().read("artifacts", Artifact)
    assert any(item.artifact_type == "API" for item in artifacts)
    assert any(item.artifact_type == "Table" for item in artifacts)
