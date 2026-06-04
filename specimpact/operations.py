from __future__ import annotations

import hashlib
import json
import re
from importlib.metadata import metadata
from importlib.resources import files
from pathlib import Path
from typing import Callable

import yaml

from specimpact.config import load_config
from specimpact.core import AmbiguousAliasError, latest_run_dir, resolve_name
from specimpact.graphrag import is_external_llm
from specimpact.store import COLLECTIONS, LocalStore


def explain_why_not(store: LocalStore, name: str) -> str:
    try:
        artifact_id = resolve_name(store, name) or name
    except AmbiguousAliasError as error:
        return str(error)
    trace = _read_trace(latest_run_dir(store) / "trace.jsonl")
    row = next(
        (
            item
            for item in trace
            if item.get("event") == "candidate" and item.get("artifact_id") == artifact_id
        ),
        None,
    )
    if not row:
        return f'Could not find trace data for "{name}".'
    state = "included" if row["included"] else "excluded"
    return (
        f'Resolved "{name}" to artifact_id: {artifact_id}\n\n'
        f"Candidate state: {state}\nReason: {row['reason']}"
    )


def project_status(store: LocalStore) -> str:
    latest_run_path = store.root / "latest_run"
    if not latest_run_path.exists():
        raise ValueError("No analysis run exists")
    latest = latest_run_path.read_text(encoding="utf-8").strip()
    config = load_config(store)
    counts = {
        collection: len(
            (store.root / f"{collection}.jsonl").read_text(encoding="utf-8").splitlines()
        )
        for collection in COLLECTIONS
    }
    return json.dumps(
        {"backend": config["backend"], "latest_run": latest, "counts": counts},
        indent=2,
    )


def privacy_doctor(store: LocalStore) -> str:
    path = store.root / "config.yml"
    if not path.is_file():
        raise ValueError("SpecImpact state is not initialized")
    try:
        config = load_config(store)
    except ValueError:
        raise
    backend = config["backend"]
    llm = config["llm"]
    backend_status = (
        "ok"
        if backend == "local"
        else "optional backend selected"
        if backend == "neo4j"
        else f"unknown backend: {backend}"
    )
    return "\n".join(
        [
            "Privacy doctor",
            f"- Local backend: {backend_status}",
            f"- External LLM configured: {'yes' if is_external_llm(llm) else 'no'}",
            "- Document chunks leave this machine by default: "
            f"{'yes, with per-command approval' if is_external_llm(llm) else 'no'}",
        ]
    )


def evaluate_latest(store: LocalStore, expected_path: Path) -> dict[str, float | int]:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    report = json.loads((latest_run_dir(store) / "report.json").read_text(encoding="utf-8"))
    must_expected = set(expected.get("must_review", []))
    should_expected = set(expected.get("should_review", []))
    must_actual = {item["artifact_id"] for item in report["must_review"]}
    should_actual = {item["artifact_id"] for item in report["should_review"]}
    visible_expected = must_expected | should_expected
    visible_actual = must_actual | should_actual
    visible = [*report["must_review"], *report["should_review"]]
    evidence_items = [
        item for item in visible if item["evidence_ids"] or item["relation_distance"] == 0
    ]
    return {
        "must_review_recall": _recall(must_expected, must_actual),
        "should_review_recall": _recall(should_expected, should_actual),
        "evidence_coverage": len(evidence_items) / len(visible) if visible else 1.0,
        "report_size": len(visible),
        "visible_precision": _precision(visible_expected, visible_actual),
        "candidate_expansion_ratio": len(visible_actual) / len(visible_expected)
        if visible_expected
        else 0.0,
    }


def evaluate_dataset(
    store: LocalStore,
    manifest_path: Path,
    categories: set[str] | None = None,
    *,
    yes: bool = False,
    no_llm: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> dict[str, object]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    results = []
    for case in manifest["cases"]:
        if categories and case["category"] not in categories:
            continue
        change = (manifest_path.parent / case["change"]).resolve()
        expected = (manifest_path.parent / case["expected"]).resolve()
        case_store = store
        if case.get("docs"):
            from specimpact.core import analyze_change, ingest_documents

            slug = re.sub(r"[^a-z0-9]+", "_", case["case_id"].lower()).strip("_")
            case_store = LocalStore(store.root / "evaluation_runs" / slug)
            docs = (manifest_path.parent / case["docs"]).resolve()
            aliases = (manifest_path.parent / case["aliases"]).resolve()
            ingest_documents(
                case_store,
                docs,
                aliases,
                yes=yes,
                no_llm=no_llm,
                confirm=confirm,
            )
        else:
            from specimpact.core import analyze_change

        analyze_change(
            case_store,
            change,
            yes=yes,
            no_llm=no_llm,
            confirm=confirm,
        )
        metrics = evaluate_latest(case_store, expected)
        results.append(
            {
                "case_id": case["case_id"],
                "expected_id": case.get("expected_id", case["expected"]),
                "category": case["category"],
                **metrics,
            }
        )
    return {"cases": results, "case_count": len(results)}


def release_validate(
    store: LocalStore,
    manifest_path: Path,
    *,
    yes: bool = False,
    no_llm: bool = False,
    confirm: Callable[[str], bool] | None = None,
) -> dict[str, object]:
    result = evaluate_dataset(
        store,
        manifest_path,
        yes=yes,
        no_llm=no_llm,
        confirm=confirm,
    )
    cases = result["cases"]
    category_counts = {
        category: sum(case["category"] == category for case in cases)
        for category in ("golden", "evaluation", "holdout")
    }
    evaluation = [case for case in cases if case["category"] == "evaluation"]
    must_review_recall = (
        sum(case["must_review_recall"] for case in evaluation) / len(evaluation)
        if evaluation
        else 0.0
    )
    visible_precision = (
        sum(case["visible_precision"] for case in evaluation) / len(evaluation)
        if evaluation
        else 0.0
    )
    evidence_coverage = (
        sum(case["evidence_coverage"] for case in cases) / len(cases) if cases else 0.0
    )
    max_report_size = max((case["report_size"] for case in cases), default=0)
    max_expansion_ratio = max((case["candidate_expansion_ratio"] for case in cases), default=0.0)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    unique_changes = {case["change"] for case in manifest["cases"]}
    unique_expected = {
        _oracle_hash((manifest_path.parent / case["expected"]).resolve())
        for case in manifest["cases"]
    }
    checks = {
        "case_count_20_to_30": 20 <= result["case_count"] <= 30,
        "golden_cases_present": category_counts["golden"] > 0,
        "evaluation_cases_present": category_counts["evaluation"] > 0,
        "holdout_cases_present": category_counts["holdout"] > 0,
        "evaluation_must_review_recall_at_least_90_percent": must_review_recall >= 0.9,
        "evaluation_visible_precision_at_least_70_percent": visible_precision >= 0.7,
        "evidence_coverage_is_100_percent": evidence_coverage == 1.0,
        "visible_candidate_count_at_most_50": max_report_size <= 50,
        "candidate_expansion_ratio_at_most_2": max_expansion_ratio <= 2.0,
        "unique_changes_at_least_20": len(unique_changes) >= 20,
        "unique_expected_at_least_20": len(unique_expected) >= 20,
        "no_confidence_field": _reports_exclude_field(store, "confidence"),
        "no_llm_judgement_field": _reports_exclude_field(store, "llm_judgement"),
        "repository_url_configured": _repository_url_configured(),
        "security_contact_configured": _security_contact_configured(),
    }
    return {
        "status": "pass" if all(checks.values()) else "fail",
        "case_count": result["case_count"],
        "category_counts": category_counts,
        "evaluation_must_review_recall": must_review_recall,
        "evaluation_visible_precision": visible_precision,
        "evidence_coverage": evidence_coverage,
        "unique_changes": len(unique_changes),
        "unique_expected": len(unique_expected),
        "checks": checks,
    }


def _read_trace(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _recall(expected: set[str], actual: set[str]) -> float:
    return len(expected & actual) / len(expected) if expected else 1.0


def _precision(expected: set[str], actual: set[str]) -> float:
    return len(expected & actual) / len(actual) if actual else 1.0


def _reports_exclude_field(store: LocalStore, field: str) -> bool:
    reports = list(store.root.glob("evaluation_runs/*/runs/*/report.json"))
    if not reports and (store.root / "latest_run").exists():
        reports.append(latest_run_dir(store) / "report.json")
    return all(f'"{field}"' not in path.read_text(encoding="utf-8") for path in reports)


def _repository_url_configured() -> bool:
    package = metadata("specimpact")
    repository = next(
        (
            value.split(", ", 1)[1]
            for value in package.get_all("Project-URL", [])
            if value.startswith("Repository, ")
        ),
        "",
    )
    return bool(repository and "example.invalid" not in repository)


def _security_contact_configured(
    publication=None,
    security_policy: Path | None = None,
) -> bool:
    publication = publication or files("specimpact").joinpath("resources", "publication.json")
    contact = json.loads(publication.read_text(encoding="utf-8"))["security_contact"]
    if not contact or contact == "SECURITY-CONTACT-TODO":
        return False
    if security_policy is None:
        source_policy = Path(__file__).parents[1] / "SECURITY.md"
        security_policy = source_policy if source_policy.is_file() else None
    if security_policy is not None:
        text = security_policy.read_text(encoding="utf-8")
        return "SECURITY-CONTACT-TODO" not in text and contact in text
    return True


def _oracle_hash(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = json.dumps(
        _normalize_oracle(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_oracle(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _normalize_oracle(item)
            for key, item in value.items()
            if key != "case_id"
        }
    if isinstance(value, list):
        items = [_normalize_oracle(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return value
