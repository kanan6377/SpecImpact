from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from specimpact.store import LocalStore

DEFAULT_CONFIG: dict[str, Any] = {
    "backend": "local",
    "llm": {
        "enabled": False,
        "provider": None,
        "model": None,
        "base_url": None,
    },
    "embeddings": {
        "enabled": False,
        "provider": "local",
        "model": "intfloat/multilingual-e5-small",
    },
    "retrieval": {
        "semantic_top_k": 20,
        "graph_max_hops": 2,
    },
}


def load_config(store: LocalStore) -> dict[str, Any]:
    path = store.root / "config.yml"
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ValueError("Invalid config YAML") from error
    if not isinstance(raw, dict):
        raise ValueError("config.yml must contain a mapping")
    config = deepcopy(DEFAULT_CONFIG)
    _merge(config, raw)
    if not isinstance(config.get("backend"), str):
        raise ValueError("config.yml must contain a backend string")
    return config


def save_config(store: LocalStore, config: dict[str, Any]) -> None:
    store.init()
    store.write_text(
        store.root / "config.yml",
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
    )


def _merge(target: dict[str, Any], updates: dict[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = value
