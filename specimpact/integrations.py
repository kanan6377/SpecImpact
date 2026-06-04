from __future__ import annotations

import json
import shutil
from pathlib import Path

from specimpact.config import load_config, save_config
from specimpact.core import latest_run_dir
from specimpact.models import Relation
from specimpact.store import LocalStore


def configure_backend(store: LocalStore, backend: str, uri: str | None = None) -> None:
    if backend not in {"local", "neo4j"}:
        raise ValueError("backend must be local or neo4j")
    if backend == "neo4j" and not uri:
        raise ValueError("neo4j backend requires --uri")
    config = load_config(store)
    config["backend"] = backend
    config.pop("neo4j_uri", None)
    if uri:
        config["neo4j_uri"] = uri
    save_config(store, config)


def export_obsidian(store: LocalStore, output_dir: Path) -> Path:
    run_dir = latest_run_dir(store)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"specimpact-{run_dir.name}.md"
    shutil.copyfile(run_dir / "report.md", target)
    return target


def import_review_results(store: LocalStore, path: Path) -> int:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("review result file must contain a JSON list")
    target = store.root / "review_results.jsonl"
    store.write_text(
        target,
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
    )
    return len(rows)


def create_baseline(store: LocalStore, name: str) -> Path:
    target = store.root / "baselines" / f"{name}.relations.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(store.root / "relations.jsonl", target)
    return target


def graph_diff(store: LocalStore, name: str) -> dict[str, list[str]]:
    baseline_path = store.root / "baselines" / f"{name}.relations.jsonl"
    baseline = {
        Relation.model_validate_json(line).relation_id
        for line in baseline_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    current = {item.relation_id for item in store.read("relations", Relation)}
    return {"added": sorted(current - baseline), "removed": sorted(baseline - current)}
