from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from jsonschema.exceptions import ValidationError
from openpyxl import Workbook
from typer.testing import CliRunner

from specimpact.cli import app
from specimpact.core import analyze_change, explain_why, ingest_documents, resolve_name
from specimpact.extraction import AliasCatalog
from specimpact.inspection import decide_alias, set_relation_status
from specimpact.loaders import load_document
from specimpact.models import Artifact, Chunk, Document, Evidence, Relation, Section
from specimpact.operations import _security_contact_configured, privacy_doctor
from specimpact.schema_validation import validate_evidence
from specimpact.store import LocalStore
from specimpact.structured_loaders import ingest_ddl, ingest_openapi
from specimpact.tabular_loaders import ingest_csv, ingest_excel

ROOT = Path(__file__).parents[1]
ENROLLMENT = ROOT / "examples" / "credit_card_enrollment"
PAYMENT = ROOT / "examples" / "payment_processing"
runner = CliRunner()


def test_unknown_domain_markdown_parser(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, PAYMENT / "docs", PAYMENT / "aliases.yml")
    report = analyze_change(store, PAYMENT / "changes" / "change_payment_amount.md")
    expected = json.loads(
        (PAYMENT / "expected" / "change_payment_amount.expected.json").read_text(encoding="utf-8")
    )
    grouped = report.grouped()
    for priority in ("must_review", "should_review", "may_review"):
        assert {item["artifact_id"] for item in grouped[priority]} == set(expected[priority])


def test_multiple_entities_and_rejected_relation(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    change = tmp_path / "multi.md"
    change.write_text(
        "# 年収と住所の変更\n\nannualIncome と address を変更する。",
        encoding="utf-8",
    )
    report = analyze_change(store, change)
    assert report.change.changed_entity_ids == [
        "entity.application.address",
        "entity.application.annual_income",
    ]
    relation = next(
        item
        for item in store.read("relations", Relation)
        if item.source_id == "api.card_application.submit"
        and item.target_id == "entity.application.address"
    )
    set_relation_status(store, relation.relation_id, "rejected")
    report = analyze_change(store, change)
    api = next(item for item in report.impacts if item.artifact_id == "api.card_application.submit")
    assert "rejected" not in api.relation_statuses


def test_rejected_relation_is_excluded_and_explained(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    relation = next(
        item
        for item in store.read("relations", Relation)
        if item.source_id == "external_if.identity_verification"
        and item.target_id == "entity.application.address"
    )
    set_relation_status(store, relation.relation_id, "rejected")
    report = analyze_change(store, ENROLLMENT / "changes" / "change_address_required_rule.md")
    assert "external_if.identity_verification" not in {item.artifact_id for item in report.impacts}
    explanation = explain_why(store, "本人確認サービス")
    assert "Candidate state: excluded" in explanation
    assert "Rejected relations" in explanation


def test_alias_collision_and_immediate_update(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    decide_alias(store, "api.card_application.submit", "new-submit-api", "approved")
    assert resolve_name(store, "new-submit-api") == "api.card_application.submit"
    artifact = next(
        item
        for item in store.read("artifacts", Artifact)
        if item.artifact_id == "api.card_application.submit"
    )
    assert "new-submit-api" in artifact.aliases
    assert (
        resolve_name(store, "requested_credit_limit")
        == "entity.application.requested_credit_limit"
    )


def test_sections_are_persisted_and_references_are_valid(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    documents = {item.document_id for item in store.read("documents", Document)}
    sections = {item.section_id: item for item in store.read("sections", Section)}
    chunks = {item.chunk_id: item for item in store.read("chunks", Chunk)}
    for evidence in store.read("evidence", Evidence):
        assert evidence.document_id in documents
        assert evidence.section_id in sections
        assert evidence.chunk_id in chunks


def test_structured_merge_and_config_preservation(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    store.write_text(store.root / "config.yml", "backend: neo4j\nneo4j_uri: bolt://localhost\n")
    ingest_documents(store, ENROLLMENT / "docs")
    assert "backend: neo4j" in (store.root / "config.yml").read_text(encoding="utf-8")
    initial = len(store.read("artifacts", Artifact))
    source = ENROLLMENT / "structured" / "card_application.openapi.yml"
    ingest_openapi(store, source)
    once = len(store.read("artifacts", Artifact))
    ingest_openapi(store, source)
    twice = len(store.read("artifacts", Artifact))
    assert once > initial
    assert twice == once
    relation = next(
        item for item in store.read("relations", Relation) if item.relation_type == "REQUEST_FIELD"
    )
    set_relation_status(store, relation.relation_id, "confirmed")
    ingest_openapi(store, source)
    statuses = {item.relation_id: item.status for item in store.read("relations", Relation)}
    assert statuses[relation.relation_id] == "confirmed"


def test_multiple_structured_sources_merge(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    first = tmp_path / "first.yml"
    second = tmp_path / "second.yml"
    first.write_text(_openapi("submitFirst"), encoding="utf-8")
    second.write_text(_openapi("submitSecond"), encoding="utf-8")
    ingest_openapi(store, first)
    ingest_openapi(store, second)
    api_names = {
        item.display_name
        for item in store.read("artifacts", Artifact)
        if item.artifact_type == "API"
    }
    assert {"submitFirst", "submitSecond"} <= api_names


def test_same_name_structured_sources_fail_fast(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    first = tmp_path / "first" / "api.yml"
    second = tmp_path / "second" / "api.yml"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text(_openapi("submitFirst"), encoding="utf-8")
    second.write_text(_openapi("submitSecond"), encoding="utf-8")
    ingest_openapi(store, first)
    with pytest.raises(ValueError, match="Document ID collision"):
        ingest_openapi(store, second)
    assert {
        item.display_name
        for item in store.read("artifacts", Artifact)
        if item.artifact_type == "API"
    } == {"submitFirst"}


def test_same_name_csv_sources_fail_fast(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    first = tmp_path / "first" / "fields.csv"
    second = tmp_path / "second" / "fields.csv"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("first\nvalue\n", encoding="utf-8")
    second.write_text("second\nvalue\n", encoding="utf-8")
    ingest_csv(store, first)
    with pytest.raises(ValueError, match="Document ID collision"):
        ingest_csv(store, second)
    assert {item.display_name for item in store.read("artifacts", Artifact)} == {
        "fields",
        "fields.first",
    }


def test_document_ids_include_path_hash(tmp_path: Path) -> None:
    left = tmp_path / "left" / "01_same.md"
    right = tmp_path / "right" / "02_same.md"
    left.parent.mkdir()
    right.parent.mkdir()
    left.write_text("# Left", encoding="utf-8")
    right.write_text("# Right", encoding="utf-8")
    assert load_document(left)[0].document_id != load_document(right)[0].document_id


def test_document_ids_are_stable_across_clone_roots(tmp_path: Path) -> None:
    left = tmp_path / "left" / "docs" / "api.md"
    right = tmp_path / "right" / "docs" / "api.md"
    left.parent.mkdir(parents=True)
    right.parent.mkdir(parents=True)
    left.write_text("# API: Example", encoding="utf-8")
    right.write_text("# API: Example", encoding="utf-8")
    assert load_document(left, source_key="api.md")[0].document_id == load_document(
        right, source_key="api.md"
    )[0].document_id


def test_change_request_requires_heading_and_why_direct_unresolved(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, ENROLLMENT / "docs", ENROLLMENT / "aliases.yml")
    invalid = tmp_path / "invalid.md"
    invalid.write_text("no heading", encoding="utf-8")
    with pytest.raises(ValueError, match="Markdown heading"):
        analyze_change(store, invalid)
    analyze_change(store, ENROLLMENT / "changes" / "change_address_required_rule.md")
    assert "no relation evidence is required" in explain_why(store, "住所")
    assert "Could not resolve" in explain_why(store, "missing-item")


def test_schema_files_are_valid_json() -> None:
    for path in (ROOT / "schemas" / "v1").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert payload["$id"].startswith("urn:specimpact:schema:v1:")
        assert "example.invalid" not in path.read_text(encoding="utf-8")
    assert not list((ROOT / "specimpact" / "resources" / "schemas" / "v1").glob("*.json"))


def test_runtime_schema_rejects_invalid_nested_evidence() -> None:
    with pytest.raises(ValidationError):
        validate_evidence(
            {
                "evidence_id": "ev.invalid",
                "document_id": "doc.invalid",
                "section_id": "sec.invalid",
                "chunk_id": "chunk.invalid",
                "quote": "invalid",
                "evidence_type": "plain_mention",
                "supports": [{}],
                "source_location": {"file": "invalid.md", "line_start": 1, "line_end": 1},
            }
        )


def test_ddl_csv_and_excel_join_common_graph(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    structured = ENROLLMENT / "structured"
    ingest_ddl(store, structured / "schema.sql")
    ingest_csv(store, structured / "card_application_fields.csv")
    workbook_path = tmp_path / "fields.xlsx"
    workbook = Workbook()
    workbook.active.append(["paymentAmount", "merchantId"])
    workbook.active.append([100, "m-1"])
    workbook.save(workbook_path)
    ingest_excel(store, workbook_path)
    documents = store.read("documents", Document)
    artifacts = store.read("artifacts", Artifact)
    assert {item.document_type for item in documents} == {"ddl", "csv", "excel"}
    assert any(item.artifact_type == "Column" for item in artifacts)


def test_invalid_alias_yaml_and_missing_path_are_input_errors(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    aliases = tmp_path / "aliases.yml"
    aliases.write_text("aliases: [", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid aliases YAML"):
        ingest_documents(store, PAYMENT / "docs", aliases)
    with pytest.raises(ValueError, match="does not exist"):
        ingest_documents(store, tmp_path / "missing")


@pytest.mark.parametrize(
    "content",
    [
        "aliases:\n  api.a: []\n",
        "aliases:\n  api.a: {canonical_type: API, aliases: Alias}\n",
        "aliases:\n  api.a: {canonical_type: Unknown, aliases: []}\n",
    ],
)
def test_alias_entries_require_typed_mappings(content: str) -> None:
    with pytest.raises(ValueError):
        AliasCatalog.parse(content)


def test_cross_type_alias_collision_is_rejected() -> None:
    with pytest.raises(ValueError, match="Ambiguous alias"):
        AliasCatalog.parse(
            "aliases:\n"
            "  api.shared: {canonical_type: API, aliases: [Shared]}\n"
            "  table.shared: {canonical_type: Table, aliases: [Shared]}\n"
        )


def test_failed_markdown_ingest_keeps_all_state_unchanged(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "api.md").write_text("# API: First API\n", encoding="utf-8")
    (second / "api.md").write_text("# API: Second API\n", encoding="utf-8")
    first_aliases = tmp_path / "first-aliases.yml"
    second_aliases = tmp_path / "second-aliases.yml"
    first_aliases.write_text("aliases: {}\n", encoding="utf-8")
    second_aliases.write_text(
        "aliases:\n  api.second: {canonical_type: API, aliases: [Second API]}\n",
        encoding="utf-8",
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, first, first_aliases)
    before = _state_snapshot(store)
    with pytest.raises(ValueError, match="Document ID collision"):
        ingest_documents(store, second, second_aliases)
    assert _state_snapshot(store) == before


def test_removed_document_is_pruned_on_reingest(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    shutil.copytree(PAYMENT / "docs", docs)
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs, PAYMENT / "aliases.yml")
    assert len(store.read("documents", Document)) == 3
    (docs / "03_external_interfaces.md").unlink()
    ingest_documents(store, docs)
    assert len(store.read("documents", Document)) == 2
    assert "external_if.payment.fraud_gateway" not in {
        item.artifact_id for item in store.read("artifacts", Artifact)
    }


def test_duplicate_relation_evidence_support_is_normalized(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "api.md").write_text(
        "# API: Duplicate API\n\n## Request fields\n- amount\n- amount\n",
        encoding="utf-8",
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, docs)
    relation_ids = {item.relation_id for item in store.read("relations", Relation)}
    for evidence in store.read("evidence", Evidence):
        supports = [item.id for item in evidence.supports if item.type == "relation"]
        assert set(supports) <= relation_ids


def test_alias_collision_fails_during_ingest_without_overwrite(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    ingest_documents(store, PAYMENT / "docs", PAYMENT / "aliases.yml")
    previous = (store.root / "aliases.yml").read_text(encoding="utf-8")
    aliases = tmp_path / "aliases.yml"
    aliases.write_text(
        "aliases:\n"
        "  entity.one: {canonical_type: BusinessField, aliases: [amount]}\n"
        "  entity.two: {canonical_type: BusinessField, aliases: [amount]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Ambiguous alias"):
        ingest_documents(store, PAYMENT / "docs", aliases)
    assert (store.root / "aliases.yml").read_text(encoding="utf-8") == previous


def test_structured_evidence_line_and_invalid_mapping(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    path = ENROLLMENT / "structured" / "card_application.openapi.yml"
    ingest_openapi(store, path)
    evidence = next(
        item for item in store.read("evidence", Evidence) if item.quote == "requestedCreditLimit"
    )
    assert evidence.source_location.line_start == 15
    invalid = tmp_path / "invalid.yml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a mapping"):
        ingest_openapi(store, invalid)


@pytest.mark.parametrize(
    "content",
    [
        "openapi: 3.0.0\npaths: []\n",
        "openapi: 3.0.0\npaths:\n  /api/items: []\n",
        "openapi: 3.0.0\npaths:\n  /api/items:\n    post:\n",
        "openapi: 3.0.0\npaths:\n  /api/items:\n    post:\n      responses: []\n",
    ],
)
def test_malformed_openapi_nested_mappings_are_input_errors(
    tmp_path: Path,
    content: str,
) -> None:
    source = tmp_path / "invalid.yml"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid OpenAPI source"):
        ingest_openapi(LocalStore(tmp_path / ".specimpact"), source)


def test_openapi_scalar_method_key_is_ignored_without_traceback(tmp_path: Path) -> None:
    source = tmp_path / "api.yml"
    source.write_text(
        "openapi: 3.0.3\n"
        "paths:\n"
        "  /api/items:\n"
        "    200: ignored\n"
        "    post:\n"
        "      operationId: submitItem\n"
        "      responses: {}\n",
        encoding="utf-8",
    )
    records = ingest_openapi(LocalStore(tmp_path / ".specimpact"), source)
    assert [item["display_name"] for item in records] == ["submitItem"]


@pytest.mark.parametrize(
    "content",
    [
        (
            "openapi: 3.0.3\n"
            "paths:\n"
            "  /api/items:\n"
            "    post:\n"
            "      operationId: [invalid]\n"
            "      responses: {}\n"
        ),
        (
            "openapi: 3.0.3\n"
            "paths:\n"
            "  /api/items:\n"
            "    post:\n"
            "      requestBody:\n"
            "        content:\n"
            "          application/json:\n"
            "            schema:\n"
            "              properties:\n"
            "                123: {type: string}\n"
            "      responses: {}\n"
        ),
        (
            "openapi: 3.0.3\n"
            "components:\n"
            "  schemas:\n"
            "    Valid: {}\n"
            "    123: {}\n"
            "paths: {}\n"
        ),
    ],
)
def test_openapi_invalid_leaf_types_are_cli_input_errors(
    tmp_path: Path,
    monkeypatch,
    content: str,
) -> None:
    source = tmp_path / "invalid.yml"
    source.write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ingest-openapi", str(source)])
    assert result.exit_code == 2
    assert "Invalid OpenAPI source" in result.output
    assert "Traceback" not in result.output


def test_openapi_evidence_lines_are_scoped_to_request_and_response(tmp_path: Path) -> None:
    source = tmp_path / "api.yml"
    text = """
openapi: 3.0.3
info:
  title: status
paths:
  /api/status:
    post:
      operationId: updateStatus
      requestBody:
        content:
          application/json:
            schema:
              properties:
                status: {type: string}
      responses:
        "200":
          content:
            application/json:
              schema:
                properties:
                  status: {type: string}
"""
    source.write_text(text, encoding="utf-8")
    store = LocalStore(tmp_path / ".specimpact")
    ingest_openapi(store, source)
    evidence = {
        item.evidence_type: item.source_location.line_start
        for item in store.read("evidence", Evidence)
        if item.quote == "status"
    }
    occurrences = [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if line.strip() == "status: {type: string}"
    ]
    assert evidence == {
        "api_request_definition": occurrences[0],
        "api_response_definition": occurrences[1],
    }


def test_ddl_evidence_lines_are_scoped_to_each_table(tmp_path: Path) -> None:
    source = tmp_path / "schema.sql"
    source.write_text(
        "CREATE TABLE FIRST_TABLE (\n"
        "  id INTEGER\n"
        ");\n"
        "CREATE TABLE SECOND_TABLE (\n"
        "  id INTEGER\n"
        ");\n",
        encoding="utf-8",
    )
    store = LocalStore(tmp_path / ".specimpact")
    ingest_ddl(store, source)
    lines = sorted(
        item.source_location.line_start
        for item in store.read("evidence", Evidence)
        if item.quote == "id INTEGER"
    )
    assert lines == [2, 5]


@pytest.mark.parametrize("content", [b"not a zip file", b"PK extension only"])
def test_invalid_excel_sources_are_input_errors(tmp_path: Path, content: bytes) -> None:
    source = tmp_path / "bad.xlsx"
    source.write_bytes(content)
    with pytest.raises(ValueError, match="Invalid Excel source"):
        ingest_excel(LocalStore(tmp_path / ".specimpact"), source)


def test_schema_build_sync_removes_deleted_output_schema(tmp_path: Path) -> None:
    build_lib = tmp_path / "build"
    command = [sys.executable, "setup.py", "build_py", "--build-lib", str(build_lib)]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    target = build_lib / "specimpact" / "resources" / "schemas" / "v1"
    removed = target / "removed.schema.json"
    removed.write_text("{}\n", encoding="utf-8")
    subprocess.run([*command, "--force"], cwd=ROOT, check=True, capture_output=True, text=True)
    assert not removed.exists()


def test_security_contact_gate_checks_source_policy(tmp_path: Path) -> None:
    publication = tmp_path / "publication.json"
    policy = tmp_path / "SECURITY.md"
    publication.write_text('{"security_contact": "security@example.test"}\n', encoding="utf-8")
    policy.write_text("`SECURITY-CONTACT-TODO`\n", encoding="utf-8")
    assert not _security_contact_configured(publication, policy)
    policy.write_text("security@example.test\n", encoding="utf-8")
    assert _security_contact_configured(publication, policy)


def test_privacy_doctor_parses_backend_exactly(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    store.write_text(store.root / "config.yml", "backend: localish\n")
    output = privacy_doctor(store)
    assert "unknown backend: localish" in output
    assert "Local backend: ok" not in output
    store.write_text(store.root / "config.yml", "backend: [\n")
    with pytest.raises(ValueError, match="Invalid config YAML"):
        privacy_doctor(store)


def test_init_only_cli_commands_report_user_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    for command in (["report"], ["why-not", "missing"], ["status"]):
        result = runner.invoke(app, command)
        assert result.exit_code == 2
        assert "No analysis run exists" in result.output


def test_cli_input_errors_do_not_show_tracebacks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    doctor = runner.invoke(app, ["doctor", "--privacy"])
    assert doctor.exit_code == 2
    assert "SpecImpact state is not initialized" in doctor.output
    assert "Traceback" not in doctor.output
    runner.invoke(app, ["init"])
    missing = runner.invoke(app, ["aliases", "add", "missing.target", "alias-value"])
    assert missing.exit_code == 2
    assert "Unknown alias target" in missing.output
    assert "Traceback" not in missing.output


def test_malformed_loader_cli_errors_do_not_show_tracebacks(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    openapi = tmp_path / "invalid.yml"
    excel = tmp_path / "bad.xlsx"
    openapi.write_text("openapi: 3.0.0\npaths: []\n", encoding="utf-8")
    excel.write_bytes(b"not a zip file")
    for command, message in (
        (["ingest-openapi", str(openapi)], "Invalid OpenAPI source"),
        (["ingest-excel", str(excel)], "Invalid Excel source"),
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 2
        assert message in result.output
        assert "Traceback" not in result.output


def test_wheel_install_release_check_has_packaged_resources(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    site = tmp_path / "site"
    dist.mkdir()
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", str(ROOT), "--no-deps", "-w", str(dist)],
            check=True,
            capture_output=True,
            text=True,
        )
        wheel = next(dist.glob("specimpact-*.whl"))
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            for schema in (ROOT / "schemas" / "v1").glob("*.json"):
                packaged = archive.read(f"specimpact/resources/schemas/v1/{schema.name}")
                assert packaged == schema.read_bytes()
        assert "specimpact/resources/publication.json" in names
        assert "specimpact/resources/schemas/v1/report.schema.json" in names
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(site),
                str(wheel),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        env = {**os.environ, "PYTHONPATH": str(site)}
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "specimpact",
                "release-check",
                str(ROOT / "examples" / "evaluation" / "release_cases.yml"),
            ],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert json.loads(result.stdout)["checks"]["unique_expected_at_least_20"]
        assert "Traceback" not in result.stderr
    finally:
        shutil.rmtree(ROOT / "build", ignore_errors=True)


def _openapi(operation_id: str) -> str:
    return f"""
openapi: 3.0.3
paths:
  /api/{operation_id}:
    post:
      operationId: {operation_id}
      requestBody:
        content:
          application/json:
            schema:
              properties:
                paymentAmount: {{type: integer}}
      responses: {{}}
"""


def _state_snapshot(store: LocalStore) -> dict[str, bytes]:
    return {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in store.root.rglob("*")
        if path.is_file()
    }
