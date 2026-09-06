"""Fetch the pinned, evidence-oriented Fintan benchmark corpus."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from specimpact.dirty_excel.ingestion import ingest_dirty_excel
from specimpact.impact_management.review_session import analyze_change_llm_first
from specimpact.models import Evidence
from specimpact.store import LocalStore

FINTAN_REPOSITORY = "https://github.com/Fintan-contents/spring-sample-project.git"
FINTAN_COMMIT = "a0ce5854ac0b40025e89a5319c9157ef07650b65"
CELL_RANGE_PATTERN = re.compile(
    r"\[[^\]\r\n!]+![A-Z]{1,3}[1-9]\d*(?::[A-Z]{1,3}[1-9]\d*)?\]"
)


class FintanManifestError(ValueError):
    """Raised when a Fintan manifest is unsafe or malformed."""


def _run_git(args: list[str], cwd: Path, *, input: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=input,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def _validate_relative_path(value: Any, field: str, *, filename_only: bool = False) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise FintanManifestError(f"{field} must be a non-empty POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise FintanManifestError(f"{field} contains an unsafe path: {value!r}")
    if filename_only and len(path.parts) != 1:
        raise FintanManifestError(f"{field} must be a local filename: {value!r}")
    return value


def _load_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, str]]]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise FintanManifestError("manifest must be a mapping")
    metadata = document.get("metadata")
    files = document.get("files")
    if not isinstance(metadata, dict) or not isinstance(files, list):
        raise FintanManifestError("manifest requires metadata and files")
    if metadata.get("repository") != FINTAN_REPOSITORY or metadata.get("commit") != FINTAN_COMMIT:
        raise FintanManifestError("manifest must pin the supported Fintan repository and commit")
    expected_count = metadata.get("file_count", 21)
    if not isinstance(expected_count, int) or len(files) != expected_count:
        raise FintanManifestError(f"manifest must contain exactly {expected_count} files")

    entries: list[dict[str, str]] = []
    local_names: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise FintanManifestError(f"files[{index}] must be a mapping")
        source_path = _validate_relative_path(
            item.get("source_path"), f"files[{index}].source_path"
        )
        local_filename = _validate_relative_path(
            item.get("local_filename"), f"files[{index}].local_filename", filename_only=True
        )
        if local_filename in local_names:
            raise FintanManifestError(f"duplicate local filename: {local_filename}")
        local_names.add(local_filename)
        entries.append({"source_path": source_path, "local_filename": local_filename})
    return metadata, entries


def fetch_fintan_corpus(manifest_path: str | Path, output_dir: str | Path) -> Path:
    """Extract manifest-selected blobs from the pinned Fintan commit.

    The repository is fetched into a temporary git directory and never checked out.
    Returns the output directory containing the workbooks and ``provenance.json``.
    """

    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    metadata, entries = _load_manifest(manifest_path)

    with tempfile.TemporaryDirectory(prefix="specimpact-fintan-") as temporary:
        git_dir = Path(temporary)
        _run_git(["init", "--quiet"], git_dir)
        _run_git(["remote", "add", "origin", metadata["repository"]], git_dir)
        _run_git(
            ["fetch", "--quiet", "--no-tags", "--depth", "1", "origin", metadata["commit"]],
            git_dir,
        )
        fetched_commit = _run_git(["rev-parse", "FETCH_HEAD^{commit}"], git_dir).decode().strip()
        if fetched_commit != metadata["commit"]:
            raise RuntimeError(f"fetched commit {fetched_commit!r} does not match the manifest pin")

        staged = output_dir.with_name(f"{output_dir.name}.tmp")
        if staged.exists():
            raise FileExistsError(f"temporary output already exists: {staged}")
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staged.mkdir(parents=True)
        provenance_files: list[dict[str, str]] = []
        try:
            for entry in entries:
                content = _run_git(
                    ["show", f"{metadata['commit']}:{entry['source_path']}"], git_dir
                )
                destination = staged / entry["local_filename"]
                destination.write_bytes(content)
                provenance_files.append(
                    {
                        **entry,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            provenance = {
                "repository": metadata["repository"],
                "commit": metadata["commit"],
                "license": metadata.get("license"),
                "license_url": metadata.get("license_url"),
                "attribution": metadata.get("attribution"),
                "scenario": metadata.get("scenario"),
                "files": provenance_files,
            }
            (staged / "provenance.json").write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            staged.replace(output_dir)
        except Exception:
            for child in staged.iterdir():
                child.unlink()
            staged.rmdir()
            raise
    return output_dir


def _validate_corpus_provenance(corpus_dir: Path, provenance: dict[str, Any]) -> None:
    """Verify that the fetched workbook set still matches its recorded provenance."""

    files = provenance.get("files")
    if not isinstance(files, list):
        raise ValueError("Fintan corpus provenance must contain a files list")
    expected: dict[str, str] = {}
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            raise ValueError(f"Fintan provenance files[{index}] must be a mapping")
        try:
            local_filename = _validate_relative_path(
                entry["local_filename"],
                f"provenance.files[{index}].local_filename",
                filename_only=True,
            )
            digest = entry["sha256"]
        except (KeyError, FintanManifestError) as exc:
            raise ValueError(f"Invalid Fintan provenance entry at index {index}") from exc
        if (
            not isinstance(digest, str)
            or len(digest) != hashlib.sha256().digest_size * 2
            or any(char not in "0123456789abcdef" for char in digest.lower())
        ):
            raise ValueError(f"Invalid SHA-256 for provenance file {local_filename}")
        if local_filename in expected:
            raise ValueError(f"Duplicate Fintan provenance filename: {local_filename}")
        expected[local_filename] = digest.lower()

    actual = {
        path.relative_to(corpus_dir).as_posix()
        for path in corpus_dir.rglob("*.xlsx")
        if path.is_file()
    }
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise ValueError(
            f"Fintan corpus files do not match provenance (missing={missing}, extra={extra})"
        )
    for local_filename, expected_digest in expected.items():
        actual_digest = hashlib.sha256((corpus_dir / local_filename).read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ValueError(f"SHA-256 mismatch for Fintan corpus file {local_filename}")


def run_fintan_benchmark(
    corpus_dir: str | Path,
    workspace_dir: str | Path,
    *,
    aliases_path: str | Path,
    change_path: str | Path,
    expected_path: str | Path,
) -> dict[str, Any]:
    """Run the deterministic evidence-index benchmark against a fetched Fintan subset."""

    corpus_dir = Path(corpus_dir)
    workspace_dir = Path(workspace_dir)
    provenance_path = corpus_dir / "provenance.json"
    if not provenance_path.is_file():
        raise ValueError("Fintan corpus must contain provenance.json from fetch_fintan_corpus")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if (
        provenance.get("repository") != FINTAN_REPOSITORY
        or provenance.get("commit") != FINTAN_COMMIT
    ):
        raise ValueError("Fintan corpus provenance does not match the supported pinned source")
    _validate_corpus_provenance(corpus_dir, provenance)
    if (workspace_dir / ".specimpact").exists():
        raise FileExistsError("benchmark workspace already contains .specimpact state")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    store = LocalStore(workspace_dir / ".specimpact")
    started = time.perf_counter()
    summary = ingest_dirty_excel(
        store,
        corpus_dir,
        Path(aliases_path),
        use_llm=False,
    )
    ingest_seconds = time.perf_counter() - started
    started = time.perf_counter()
    report = analyze_change_llm_first(store, Path(change_path), no_llm=True)
    analyze_seconds = time.perf_counter() - started
    result = evaluate_fintan_run(store, Path(expected_path))
    result.update(
        {
            "mode": "deterministic_evidence_index",
            "llm_used": False,
            "run_id": report.run_id,
            "ingest_seconds": round(ingest_seconds, 3),
            "analyze_seconds": round(analyze_seconds, 3),
            "ingest_summary": summary.model_dump(),
            "source": {
                "repository": provenance["repository"],
                "commit": provenance["commit"],
                "file_count": len(provenance.get("files", [])),
            },
        }
    )
    store.write_json(store.root / "fintan_benchmark_result.json", result)
    return result


def evaluate_fintan_run(store: LocalStore, expected_path: Path) -> dict[str, Any]:
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    run_id = (store.root / "latest_run").read_text(encoding="utf-8").strip()
    report = json.loads((store.root / "runs" / run_id / "report.json").read_text(encoding="utf-8"))
    evidence = {item.evidence_id: item for item in store.read("evidence", Evidence)}
    impacts = [
        item
        for group in ("must_review", "should_review", "may_review")
        for item in report.get(group, [])
    ]
    evidence_by_file: dict[str, list[Evidence]] = {}
    evidence_backed = 0
    cell_addressed = 0
    for impact in impacts:
        selected = [evidence[item] for item in impact.get("evidence_ids", []) if item in evidence]
        if selected:
            evidence_backed += 1
        if selected and all(_has_cell_range(item.quote) for item in selected):
            cell_addressed += 1
        for item in selected:
            evidence_by_file.setdefault(Path(item.source_location.file).name, []).append(item)

    expected_files = set(expected["expected_impacted_files"])
    negative_files = set(expected["negative_control_files"])
    actual_files = set(evidence_by_file)
    hits = expected_files & actual_files
    false_positive_files = actual_files - expected_files
    anchors = expected.get("evidence_anchors", [])
    missed_anchors = [
        anchor
        for anchor in anchors
        if not any(
            anchor["sheet"] in item.quote and f"[{anchor['cell']}]" in item.quote
            for item in evidence_by_file.get(anchor["file"], [])
        )
    ]
    health_path = store.root / "dirty_excel_health.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    sheet_count = max(1, int(health.get("sheets", 0)))
    unknown_sheets = int(health.get("sheet_types", {}).get("unknown", 0))
    result = {
        "scenario_id": expected["scenario_id"],
        "status": "pass",
        "expected_file_count": len(expected_files),
        "actual_file_count": len(actual_files),
        "matched_file_count": len(hits),
        "workbook_recall": len(hits) / len(expected_files) if expected_files else 1.0,
        "workbook_precision": len(hits) / len(actual_files) if actual_files else 1.0,
        "false_positive_files": sorted(false_positive_files),
        "negative_control_files": sorted(negative_files),
        "observed_negative_control_files": sorted(negative_files & actual_files),
        "missed_files": sorted(expected_files - actual_files),
        "evidence_anchor_count": len(anchors),
        "evidence_anchor_recall": (len(anchors) - len(missed_anchors)) / len(anchors)
        if anchors
        else 1.0,
        "missed_evidence_anchors": missed_anchors,
        "impact_candidate_count": len(impacts),
        "must_review_count": len(report.get("must_review", [])),
        "should_review_count": len(report.get("should_review", [])),
        "may_review_count": len(report.get("may_review", [])),
        "evidence_coverage": evidence_backed / len(impacts) if impacts else 1.0,
        "cell_address_coverage": cell_addressed / len(impacts) if impacts else 1.0,
        "unknown_sheet_rate": unknown_sheets / sheet_count,
        "health": health,
    }
    gates = {
        "all_expected_workbooks_found": result["workbook_recall"] == 1.0,
        "negative_controls_excluded": not false_positive_files,
        "all_expected_cells_found": result["evidence_anchor_recall"] == 1.0,
        "all_candidates_have_evidence": result["evidence_coverage"] == 1.0,
        "all_evidence_is_cell_addressed": result["cell_address_coverage"] == 1.0,
        "candidate_count_at_most_60": len(impacts) <= 60,
        "unknown_sheet_rate_at_most_10_percent": result["unknown_sheet_rate"] <= 0.1,
    }
    result["gates"] = gates
    result["status"] = "pass" if all(gates.values()) else "fail"
    return result


def _has_cell_range(quote: str) -> bool:
    return CELL_RANGE_PATTERN.search(quote) is not None
