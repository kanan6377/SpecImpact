from pathlib import Path

from typer.testing import CliRunner

from specimpact.application.agent_doctor import agent_doctor
from specimpact.cli import app
from specimpact.store import LocalStore

runner = CliRunner()


def test_agent_doctor_reports_initialized_mcp_runtime(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    result = agent_doctor(tmp_path, host="cursor")
    checks = {item["name"]: item["ok"] for item in result["checks"]}
    assert checks["project_directory"] is True
    assert checks["project_initialized"] is True
    assert checks["mcp_sdk"] is True
    assert result["mcp_command"][-1] == str(tmp_path.resolve())
    assert "plugins/cursor/specimpact" in result["plugin_hint"]


def test_agent_doctor_cli_rejects_unknown_host(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["agent", "doctor", "--project", str(tmp_path), "--host", "other"],
    )
    assert result.exit_code != 0
    assert "cursor or antigravity" in result.output
