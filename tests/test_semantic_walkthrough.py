import json
import subprocess
import sys
from pathlib import Path

from specimpact.core import analyze_change, ingest_documents
from specimpact.inspection import set_relation_status
from specimpact.models import Relation
from specimpact.semantic.repository import AnalysisRepository
from specimpact.store import LocalStore

FIXTURE = Path(__file__).parents[1] / "examples" / "specification_kernel"


def test_repository_imports_without_application_being_initialized_first():
    result = subprocess.run(
        [sys.executable, "-c", "import specimpact.semantic.repository; import specimpact.cli"],
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr


def test_real_markdown_ingestion_to_typed_golden_and_replay(tmp_path):
    store = LocalStore(tmp_path / ".specimpact")
    before = {p.name: p.read_bytes() for p in (FIXTURE / "docs").glob("*.md")}
    ingest_documents(store, FIXTURE / "docs", FIXTURE / "aliases.yml")
    first = analyze_change(store, FIXTURE / "change.md", no_llm=True)
    repo = AnalysisRepository(store.root)
    assert all(case.outcome == "unresolved" for case in repo.load(first.run_id)[2].cases)
    for relation in store.read("relations", Relation):
        set_relation_status(store, relation.relation_id, "confirmed")
    final = analyze_change(store, FIXTURE / "change.md", no_llm=True)
    data, _, result = repo.load(final.run_id)
    types = {a.artifact_id: a.artifact_type for a in data.artifacts}
    outcomes = {types[c.artifact_id]: c.outcome for c in result.cases}
    assert outcomes == json.loads((FIXTURE / "expected.json").read_text())
    assert repo.replay(final.run_id) == result
    assert repo.replay(first.run_id).cases[0].outcome == "unresolved"
    assert {p.name: p.read_bytes() for p in (FIXTURE / "docs").glob("*.md")} == before
