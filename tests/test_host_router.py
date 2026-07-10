from pathlib import Path

from specimpact.application import HostContext
from specimpact.application.host_router import select_host_execution_route
from specimpact.config import save_config
from specimpact.store import LocalStore


def _host(store: LocalStore, capabilities: list[str]) -> HostContext:
    return HostContext(
        host="cursor",
        workspace_root=str(store.root.parent),
        project_id="project-1",
        capabilities=capabilities,
    )


def test_host_route_prefers_sampling_then_prepare_submit(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    assert select_host_execution_route(store, _host(store, ["sampling"]))["mode"] == (
        "host_sampling"
    )
    route = select_host_execution_route(store, _host(store, []))
    assert route == {
        "mode": "host_prepare_submit",
        "provider": "host:cursor",
        "degraded": False,
    }


def test_host_route_falls_back_to_provider_then_heuristic(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    host = _host(store, [])
    assert select_host_execution_route(
        store,
        host,
        prepare_submit_available=False,
    )["mode"] == "heuristic"
    config = {
        "backend": "local",
        "llm": {"enabled": True, "provider": "codex", "model": "default", "base_url": None},
        "embeddings": {"enabled": False, "provider": "local", "model": "test"},
        "retrieval": {"semantic_top_k": 20, "graph_max_hops": 2},
    }
    save_config(store, config)
    route = select_host_execution_route(store, host, prepare_submit_available=False)
    assert route["mode"] == "specimpact_provider"
    assert route["provider"] == "codex"
