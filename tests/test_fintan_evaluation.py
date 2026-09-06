from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from specimpact.benchmarks.fintan import (
    FINTAN_COMMIT,
    FINTAN_REPOSITORY,
    evaluate_fintan_run,
    run_fintan_benchmark,
)
from specimpact.cli import app
from specimpact.models import Evidence, EvidenceSupport, SourceLocation
from specimpact.store import LocalStore

runner = CliRunner()


def test_evaluate_fintan_run_checks_workbook_and_cell_oracles(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    evidence = Evidence(
        evidence_id="ev.project",
        document_id="doc.project",
        section_id="sec.project",
        chunk_id="chunk.project",
        quote="[positive.xlsx / Project!A1:D2] [A2] プロジェクト名 / [D2] 128",
        evidence_type="dirty_excel_cell_mention",
        supports=[EvidenceSupport(type="relation", id="rel.project")],
        source_location=SourceLocation(file="corpus/positive.xlsx", line_start=2, line_end=2),
    )
    store.write("evidence", [evidence])
    run_id = "run-fintan"
    store.write_json(
        store.root / "runs" / run_id / "report.json",
        {
            "run_id": run_id,
            "change": {},
            "must_review": [
                {
                    "artifact_id": "table.project",
                    "evidence_ids": [evidence.evidence_id],
                }
            ],
            "should_review": [],
            "may_review": [],
            "hidden": [],
        },
    )
    store.write_text(store.root / "latest_run", run_id)
    store.write_json(
        store.root / "dirty_excel_health.json",
        {"sheets": 1, "sheet_types": {"db_mapping": 1}},
    )
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps(
            {
                "scenario_id": "test",
                "expected_impacted_files": ["positive.xlsx"],
                "negative_control_files": ["negative.xlsx"],
                "evidence_anchors": [
                    {"file": "positive.xlsx", "sheet": "Project", "cell": "A2"}
                ],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_fintan_run(store, expected)

    assert result["status"] == "pass"
    assert result["workbook_recall"] == 1.0
    assert result["evidence_anchor_recall"] == 1.0


def test_benchmark_fetch_fintan_cli_smoke(monkeypatch, tmp_path: Path) -> None:
    output = tmp_path / "corpus"
    manifest = tmp_path / "manifest.yml"
    manifest.write_text("metadata: {}\nfiles: []\n", encoding="utf-8")
    monkeypatch.setattr("specimpact.cli.fetch_fintan_corpus", lambda _manifest, target: target)

    result = runner.invoke(
        app,
        ["benchmark", "fetch-fintan", str(output), "--manifest", str(manifest)],
    )

    assert result.exit_code == 0
    assert "Fetched Fintan benchmark corpus" in result.stdout


def test_benchmark_run_fintan_cli_smoke(monkeypatch, tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(
        "specimpact.cli.run_fintan_benchmark",
        lambda *_args, **_kwargs: {"status": "pass", "workbook_recall": 1.0},
    )

    result = runner.invoke(
        app,
        ["benchmark", "run-fintan", str(corpus), "--workspace", str(workspace)],
    )

    assert result.exit_code == 0
    assert '"status": "pass"' in result.stdout


def test_evaluation_counts_unexpected_workbook_as_false_positive(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    evidence = Evidence(
        evidence_id="ev.unexpected",
        document_id="doc.unexpected",
        section_id="sec.unexpected",
        chunk_id="chunk.unexpected",
        quote="[unexpected.xlsx / Project!A1] [A1] unrelated",
        evidence_type="dirty_excel_cell_mention",
        supports=[EvidenceSupport(type="relation", id="rel.unexpected")],
        source_location=SourceLocation(file="corpus/unexpected.xlsx", line_start=1, line_end=1),
    )
    store.write("evidence", [evidence])
    run_id = "run-unexpected"
    store.write_json(
        store.root / "runs" / run_id / "report.json",
        {
            "must_review": [{"evidence_ids": [evidence.evidence_id]}],
            "should_review": [],
            "may_review": [],
        },
    )
    store.write_text(store.root / "latest_run", run_id)
    store.write_json(store.root / "dirty_excel_health.json", {"sheets": 1, "sheet_types": {}})
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps(
            {
                "scenario_id": "test",
                "expected_impacted_files": ["positive.xlsx"],
                "negative_control_files": ["negative.xlsx"],
            }
        ),
        encoding="utf-8",
    )

    result = evaluate_fintan_run(store, expected)

    assert result["false_positive_files"] == ["unexpected.xlsx"]
    assert result["status"] == "fail"


def test_benchmark_rejects_invalid_provenance_before_ingestion(tmp_path: Path, monkeypatch) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "only.xlsx").write_bytes(b"content")
    (corpus / "provenance.json").write_text(
        json.dumps(
            {
                "repository": FINTAN_REPOSITORY,
                "commit": FINTAN_COMMIT,
                "files": [{"local_filename": "only.xlsx", "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )
    called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("ingestion must not run")

    monkeypatch.setattr("specimpact.benchmarks.fintan.ingest_dirty_excel", fail_if_called)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        run_fintan_benchmark(
            corpus,
            tmp_path / "workspace",
            aliases_path=tmp_path / "aliases.yml",
            change_path=tmp_path / "change.md",
            expected_path=tmp_path / "expected.json",
        )
    assert not called
