from __future__ import annotations

from typing import Any

from specimpact.application.contracts import HostContext
from specimpact.config import load_config
from specimpact.store import LocalStore


def select_host_execution_route(
    store: LocalStore,
    host: HostContext,
    *,
    prepare_submit_available: bool = True,
) -> dict[str, Any]:
    if "sampling" in host.capabilities:
        return {"mode": "host_sampling", "provider": f"host:{host.host}", "degraded": False}
    if prepare_submit_available:
        return {
            "mode": "host_prepare_submit",
            "provider": f"host:{host.host}",
            "degraded": False,
        }
    config = load_config(store).get("llm", {})
    if config.get("enabled") and config.get("provider"):
        return {
            "mode": "specimpact_provider",
            "provider": config["provider"],
            "model": config.get("model"),
            "degraded": False,
        }
    return {"mode": "heuristic", "provider": None, "degraded": True}
