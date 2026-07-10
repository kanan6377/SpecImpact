from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_readme_local_links_and_images_exist() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", readme)
    local = [
        target.split("#", 1)[0]
        for target in targets
        if target and not target.startswith(("http://", "https://", "#"))
    ]
    assert local
    assert all((ROOT / target).exists() for target in local)


def test_release_versions_and_host_documentation_are_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    assert version == "1.3.0"
    cursor = json.loads(
        (ROOT / "plugins/cursor/specimpact/.cursor-plugin/plugin.json").read_text(
            encoding="utf-8"
        )
    )
    antigravity = json.loads(
        (ROOT / "plugins/antigravity/specimpact/plugin.json").read_text(encoding="utf-8")
    )
    assert cursor["version"] == antigravity["version"] == version
    manual = (ROOT / "docs/user_manual_ja.md").read_text(encoding="utf-8")
    assert "Cursor / AntigravityのHost LLM" in manual
    assert "Codex CLI を第一候補" not in manual


def test_ci_runs_python_frontend_release_and_wheel_gates() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for command in (
        "pytest -q",
        "ruff check .",
        "compileall",
        "release-check",
        "npm run check",
        "npm run build",
        "python -m build",
    ):
        assert command in workflow
