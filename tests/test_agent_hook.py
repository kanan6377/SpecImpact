import json
from pathlib import Path

from specimpact.application.agent_hook import handle_agent_hook
from specimpact.store import LocalStore


def test_agent_hook_records_hash_only_for_workspace_design_path(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    source = tmp_path / "design.md"
    body = "private design body"
    source.write_text(body, encoding="utf-8")

    result = handle_agent_hook(
        tmp_path,
        host="cursor",
        event="post-tool-use",
        payload={"tool": "Write", "params": {"path": str(source), "content": body}},
    )

    assert result == {}
    ledger = store.root / "host_change_notifications.jsonl"
    record = json.loads(ledger.read_text(encoding="utf-8"))
    assert record["path"] == "design.md"
    assert record["host"] == "cursor"
    assert body not in ledger.read_text(encoding="utf-8")


def test_agent_hook_ignores_outside_paths_and_non_post_events(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    outside = tmp_path.parent / "outside.md"
    outside.write_text("outside", encoding="utf-8")
    handle_agent_hook(
        tmp_path,
        host="cursor",
        event="post-tool-use",
        payload={"path": str(outside)},
    )
    handle_agent_hook(
        tmp_path,
        host="cursor",
        event="pre-tool-use",
        payload={"path": "design.md"},
    )
    assert not (store.root / "host_change_notifications.jsonl").exists()
