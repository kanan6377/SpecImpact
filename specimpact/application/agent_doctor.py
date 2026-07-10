from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any, Literal


def agent_doctor(
    project_path: Path | str,
    *,
    host: Literal["cursor", "antigravity"],
) -> dict[str, Any]:
    path = Path(project_path).expanduser().resolve()
    checks = [
        _check("project_directory", path.is_dir(), str(path)),
        _check(
            "specimpact_on_path",
            bool(shutil.which("specimpact") or shutil.which("specimpact.exe")),
            "Install with `uv tool install \"specimpact[mcp,gui]\"` or pipx.",
        ),
        _check(
            "mcp_sdk",
            importlib.util.find_spec("mcp") is not None,
            "Install the `specimpact[mcp]` extra.",
        ),
        _check(
            "project_initialized",
            (path / ".specimpact" / "config.yml").is_file() if path.is_dir() else False,
            "Run `specimpact init` in the project.",
        ),
    ]
    plugin_hint = (
        "Install `plugins/cursor/specimpact` from the SpecImpact marketplace."
        if host == "cursor"
        else "Install `plugins/antigravity/specimpact` in `.agents/plugins/`."
    )
    return {
        "host": host,
        "project": str(path),
        "ready": all(item["ok"] for item in checks),
        "checks": checks,
        "plugin_hint": plugin_hint,
        "mcp_command": [
            "specimpact",
            "mcp",
            "--stdio",
            "--project",
            str(path),
        ],
    }


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}
