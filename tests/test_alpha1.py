from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import (
    ENTITY_ID,
    FakeLLMClient,
    analyze_change,
    ingest_documents,
    latest_run_dir,
    resolve_name,
)
from specimpact.loaders import chunk_sections, load_document, parse_sections
from specimpact.models import Artifact, Document, Evidence, Relation
from specimpact.store import LocalStore

ROOT = Path(__file__).parents[1]
SAMPLE = ROOT / "examples" / "credit_card_enrollment"
runner = CliRunner()


def test_markdown_and_text_loader(tmp_path: Path) -> None:
    md = tmp_path / "sample.md"
    md.write_text("# Title\n\n## Part\nbody", encoding="utf-8")
    document, sections, chunks = load_document(md)
    assert document.title == "Title"
    assert len(sections) == len(chunks) == 2
    txt = tmp_path / "sample.txt"
    txt.write_text("plain text", encoding="utf-8")
    assert load_document(txt)[0].title == "plain text"


def test_section_parser_and_chunker() -> None:
    lines = ["# One", "a", "## Two", "b"]
    sections = parse_sections("doc.x", lines)
    assert sections[0].line_end == 2
    assert chunk_sections("doc.x", sections, lines)[1].text == "## Two\nb"


def test_models_round_trip() -> None:
    models = [
        Document(document_id="doc.x", path="x.md", title="x", hash="h"),
        Artifact(artifact_id="api.x", artifact_type="API", display_name="x"),
        Relation(
            relation_id="rel.x",
            relation_type="READS",
            source_id="api.x",
            target_id="entity.x",
            evidence_ids=["ev.x"],
        ),
        Evidence(
            evidence_id="ev.x",
            document_id="doc.x",
            section_id="sec.x",
            chunk_id="chunk.x",
            quote="q",
            evidence_type="plain_mention",
            supports=[],
            source_location={"file": "x.md", "line_start": 1, "line_end": 1},
        ),
    ]
    for model in models:
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_store_and_graph_analysis(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    assert ingest_documents(store, SAMPLE / "docs", SAMPLE / "aliases.yml") == 10
    assert len(store.read("documents", Document)) == 10
    report = analyze_change(store, SAMPLE / "changes" / "change_credit_limit.md")
    grouped = report.grouped()
    expected = json.loads(
        (SAMPLE / "expected" / "change_credit_limit.expected.json").read_text(encoding="utf-8")
    )
    for priority in ("must_review", "should_review", "may_review"):
        assert {item["artifact_id"] for item in grouped[priority]} == set(expected[priority])
    assert "confidence" not in json.dumps(grouped)
    assert all(item["evidence_ids"] for item in grouped["should_review"])
    assert resolve_name(store, "カード入会申込API") == "api.card_application.submit"
    assert resolve_name(store, "希望利用限度額") == ENTITY_ID
    assert FakeLLMClient().judge("x", "y") == "unknown"
    run_dir = latest_run_dir(store)
    assert {
        "change_request.json",
        "candidates.jsonl",
        "impacts.json",
        "report.md",
        "report.json",
        "trace.jsonl",
    } <= {path.name for path in run_dir.iterdir()}


def test_cli_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert runner.invoke(app, ["init"]).exit_code == 0
    ingest = runner.invoke(
        app, ["ingest", str(SAMPLE / "docs"), "--aliases", str(SAMPLE / "aliases.yml")]
    )
    assert ingest.exit_code == 0
    assert "Ingested 10 documents" in ingest.stdout
    analyze = runner.invoke(app, ["analyze", str(SAMPLE / "changes" / "change_credit_limit.md")])
    assert analyze.exit_code == 0
    markdown = runner.invoke(app, ["report", "--format", "markdown"])
    assert markdown.exit_code == 0
    assert "## Must Review" in markdown.stdout and "## Should Review" in markdown.stdout
    report_json = runner.invoke(app, ["report", "--format", "json"])
    assert report_json.exit_code == 0 and "must_review" in report_json.stdout
    why = runner.invoke(app, ["why", "カード入会申込API"])
    assert why.exit_code == 0
    assert 'Resolved "カード入会申込API" to artifact_id: api.card_application.submit' in why.stdout
