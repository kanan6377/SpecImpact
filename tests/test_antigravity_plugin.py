from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "antigravity" / "specimpact"


def _load_json(path: Path) -> dict:
    assert path.is_file(), f"missing JSON file: {path}"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"JSON file must contain an object: {path}"
    return value


def _frontmatter(path: Path) -> dict:
    match = re.match(
        r"\A---\s*\n(.*?)\n---\s*\n", path.read_text(encoding="utf-8"), re.DOTALL
    )
    assert match, f"missing YAML frontmatter: {path}"
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict), f"frontmatter must be a mapping: {path}"
    return metadata


def _server_config(manifest: dict) -> dict:
    reference = manifest.get("mcp_config", "mcp_config.json")
    assert isinstance(reference, str)
    config = _load_json(PLUGIN_ROOT / reference)
    servers = config.get("mcpServers", config.get("servers"))
    assert isinstance(servers, dict) and servers
    server = servers.get("specimpact")
    assert isinstance(server, dict), "mcp config must define the specimpact server"
    return server


def test_antigravity_plugin_manifest_declares_package_surfaces() -> None:
    manifest = _load_json(PLUGIN_ROOT / "plugin.json")
    assert manifest.get("name") == "specimpact"
    assert isinstance(manifest.get("description"), str) and manifest["description"]
    for field in ("mcp_config", "skills", "rules", "hooks"):
        assert field in manifest, f"plugin manifest missing {field}"


def test_antigravity_mcp_config_is_workspace_scoped_and_identifies_host() -> None:
    server = _server_config(_load_json(PLUGIN_ROOT / "plugin.json"))
    assert isinstance(server.get("command"), str) and server["command"]
    args = server.get("args")
    assert isinstance(args, list)
    assert "--project" in args
    project_index = args.index("--project")
    assert project_index + 1 < len(args)
    assert args[project_index + 1] in {"${workspaceFolder}", "${workspace}"}
    env = server.get("env")
    assert isinstance(env, dict)
    assert env.get("SPECIMPACT_HOST") == "antigravity"


def test_antigravity_has_four_skills_with_description_frontmatter() -> None:
    skill_files = sorted((PLUGIN_ROOT / "skills").rglob("SKILL.md"))
    assert len(skill_files) == 4
    for path in skill_files:
        metadata = _frontmatter(path)
        assert isinstance(metadata.get("name"), str) and metadata["name"]
        assert isinstance(metadata.get("description"), str) and metadata["description"]


def test_antigravity_has_rules_and_exactly_three_artifact_templates() -> None:
    rule_files = [path for path in (PLUGIN_ROOT / "rules").rglob("*") if path.is_file()]
    assert rule_files
    assert all(path.suffix in {".md", ".mdc", ".txt"} for path in rule_files)

    template_files = sorted(
        path
        for path in PLUGIN_ROOT.rglob("*.md")
        if "template" in path.stem.lower()
        or "template" in {part.lower() for part in path.parts}
        or "artifact" in path.stem.lower()
        or "artifact" in {part.lower() for part in path.parts}
        or "artifacts" in {part.lower() for part in path.parts}
    )
    assert len(template_files) == 3
    template_text = "\n".join(path.read_text(encoding="utf-8") for path in template_files)
    for term in ("Impact", "Evidence", "status", "action"):
        assert term in template_text
    assert "JSONL" in template_text
    assert re.search(r"source[- ]of[- ]truth", template_text, re.IGNORECASE)


def test_antigravity_post_tool_use_hook_only_notifies_on_design_writes() -> None:
    hook_files = sorted(PLUGIN_ROOT.rglob("hooks.json"))
    assert len(hook_files) == 1
    payload = _load_json(hook_files[0])
    hooks = payload.get("hooks", payload)
    post_tool_use = hooks.get("PostToolUse", hooks.get("postToolUse"))
    assert isinstance(post_tool_use, list) and post_tool_use
    hook_text = json.dumps(post_tool_use)
    for tool_name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
        assert tool_name in hook_text

    commands = [
        hook.get("command", "")
        for item in post_tool_use
        if isinstance(item, dict)
        for hook in item.get("hooks", [item])
        if isinstance(hook, dict)
    ]
    assert commands and all("specimpact agent hook" in command for command in commands)
    assert all("--event post-tool-use" in command for command in commands)
    assert all("--host antigravity" in command for command in commands)
    forbidden = re.compile(r"\b(?:analy[sz]e|llm|chat|completion)\b", re.IGNORECASE)
    assert not forbidden.search(hook_text)


def test_antigravity_install_scripts_cover_workspace_and_global_setup() -> None:
    scripts = [
        path
        for path in (PLUGIN_ROOT.parent).rglob("*")
        if path.is_file() and path.suffix.lower() in {".ps1", ".sh", ".cmd", ".bat"}
    ]
    assert scripts
    text_by_name = {path.name.lower(): path.read_text(encoding="utf-8") for path in scripts}
    workspace = "\n".join(text for name, text in text_by_name.items() if "workspace" in name)
    global_install = "\n".join(text for name, text in text_by_name.items() if "global" in name)
    assert workspace, "missing workspace install script"
    assert global_install, "missing global install script"
    assert all(
        re.search(r"specimpact|mcp", text, re.IGNORECASE)
        for text in (workspace, global_install)
    )
    assert re.search(r"\.agents[/\\]+plugins", workspace)
    assert re.search(r"\.gemini[/\\]+config[/\\]+plugins", global_install)


def test_antigravity_package_contains_no_python_implementation() -> None:
    python_files = list(PLUGIN_ROOT.rglob("*.py"))
    assert not python_files, f"Antigravity package must not embed Python: {python_files}"
