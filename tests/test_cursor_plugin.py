from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
PLUGIN_ROOT = ROOT / "plugins" / "cursor"
MARKETPLACE = PLUGIN_ROOT / ".cursor-plugin" / "marketplace.json"
PLUGIN_MANIFEST = PLUGIN_ROOT / "specimpact" / ".cursor-plugin" / "plugin.json"


def _load_json(path: Path) -> dict:
    assert path.is_file(), f"missing JSON manifest: {path}"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"manifest must be an object: {path}"
    return payload


def _refs(value: object, field: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    assert isinstance(value, list), f"{field} must be a list"
    paths: list[str] = []
    for item in value:
        if isinstance(item, str):
            paths.append(item)
        else:
            assert isinstance(item, dict) and isinstance(item.get("path"), str), (
                f"{field} entries must be paths or objects with a path"
            )
            paths.append(item["path"])
    return paths


def _resolved_refs(value: object, field: str) -> list[Path]:
    paths: list[Path] = []
    base = (PLUGIN_ROOT / "specimpact").resolve()
    for reference in _refs(value, field):
        matches = list(base.glob(reference))
        assert matches, f"missing {field} reference: {reference}"
        for path in matches:
            assert path.is_relative_to(base)
            if path.is_dir() and field == "skills":
                discovered = sorted(path.glob("*/SKILL.md"))
            elif path.is_dir() and field in {"rules", "commands"}:
                discovered = sorted(child for child in path.rglob("*") if child.is_file())
            else:
                discovered = [path]
            assert discovered, f"empty {field} reference: {reference}"
            paths.extend(discovered)
    return paths


def _resolve_plugin_ref(reference: str) -> Path:
    path = (PLUGIN_ROOT / "specimpact" / reference).resolve()
    assert path.is_relative_to((PLUGIN_ROOT / "specimpact").resolve())
    return path


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert match, f"missing YAML frontmatter: {path}"
    metadata = yaml.safe_load(match.group(1))
    assert isinstance(metadata, dict), f"frontmatter must be a mapping: {path}"
    return metadata


def test_cursor_marketplace_manifest_has_required_package_entry() -> None:
    marketplace = _load_json(MARKETPLACE)
    assert isinstance(marketplace.get("name"), str) and marketplace["name"]
    plugins = marketplace.get("plugins")
    assert isinstance(plugins, list) and plugins

    specimpact_entries = [entry for entry in plugins if entry.get("name") == "specimpact"]
    assert len(specimpact_entries) == 1
    entry = specimpact_entries[0]
    assert isinstance(entry.get("source"), str) and entry["source"]
    source = (PLUGIN_ROOT / entry["source"]).resolve()
    assert source.is_relative_to(PLUGIN_ROOT.resolve())
    assert source.is_dir()


def test_cursor_plugin_manifest_declares_all_extension_surfaces() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    assert manifest.get("name") == "specimpact"

    for field in ("mcpServers", "skills", "rules", "commands", "hooks"):
        assert field in manifest, f"plugin manifest missing {field}"

    mcp_servers_ref = manifest["mcpServers"]
    if isinstance(mcp_servers_ref, str):
        mcp_config = _load_json(_resolve_plugin_ref(mcp_servers_ref))
        mcp_servers = mcp_config.get("mcpServers", mcp_config)
    else:
        mcp_servers = mcp_servers_ref
    assert isinstance(mcp_servers, dict) and mcp_servers
    for server in mcp_servers.values():
        assert isinstance(server, dict)
        assert isinstance(server.get("command"), str) and server["command"]
        assert isinstance(server.get("args"), list)
        assert isinstance(server.get("env"), dict)

    for field in ("skills", "rules", "commands"):
        assert _resolved_refs(manifest[field], field)

    hooks = manifest["hooks"]
    assert hooks
    if isinstance(hooks, str):
        assert _resolved_refs(hooks, "hooks")
    elif isinstance(hooks, list):
        assert all(path.is_file() for path in _resolved_refs(hooks, "hooks"))
    else:
        assert isinstance(hooks, dict)


def test_cursor_plugin_has_four_skills_with_required_frontmatter() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    skill_paths = _resolved_refs(manifest["skills"], "skills")
    assert len(skill_paths) == 4
    for skill_file in skill_paths:
        if skill_file.is_dir():
            skill_file /= "SKILL.md"
        assert skill_file.is_file(), f"missing skill document: {skill_file}"
        metadata = _frontmatter(skill_file)
        assert isinstance(metadata.get("name"), str) and metadata["name"]
        assert isinstance(metadata.get("description"), str) and metadata["description"]


def test_cursor_plugin_has_rules_hooks_and_three_canvas_references() -> None:
    manifest = _load_json(PLUGIN_MANIFEST)
    rule_paths = _resolved_refs(manifest["rules"], "rules")
    assert rule_paths
    assert all(path.suffix in {".md", ".mdc"} for path in rule_paths)

    canvas_files = [
        path
        for path in (PLUGIN_ROOT / "specimpact").rglob("*.md")
        if "canvas" in path.as_posix().lower()
    ]
    assert len(canvas_files) == 3
    assert all(path.read_text(encoding="utf-8").strip() for path in canvas_files)


def test_cursor_plugin_templates_define_evidence_first_source_of_truth() -> None:
    package_root = PLUGIN_ROOT / "specimpact"
    template_files = [
        path
        for path in package_root.rglob("*.md")
        if "template" in path.stem.lower()
        or "templates" in path.parts
        or "canvases" in path.parts
    ]
    assert template_files
    template_text = "\n".join(path.read_text(encoding="utf-8") for path in template_files)
    for term in ("Impact", "Evidence", "status", "action"):
        assert term in template_text
    assert "JSONL" in template_text
    assert re.search(r"source[- ]of[- ]truth", template_text, re.IGNORECASE)


def test_cursor_plugin_contains_no_python_implementation() -> None:
    python_files = list((PLUGIN_ROOT / "specimpact").rglob("*.py"))
    assert not python_files, f"Cursor package must not embed Python: {python_files}"
