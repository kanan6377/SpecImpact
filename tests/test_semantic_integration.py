import json

import pytest
from test_semantic_kernel import source
from typer.testing import CliRunner

from specimpact.application import HostContext, project_from_path
from specimpact.application.host_workflow import HostWorkflow
from specimpact.application.service import execute, report_data
from specimpact.cli import app
from specimpact.core import analyze_change
from specimpact.impact_management.change_atoms import parse_change_atoms
from specimpact.impact_management.decision_store import (
    ImpactDecision,
    set_impact_status,
)
from specimpact.impact_management.review_session import analyze_change_llm_first
from specimpact.semantic.repository import AnalysisRepository
from specimpact.store import LocalStore


def workspace(tmp_path):
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    data = source()
    for name in ["documents", "entities", "artifacts", "relations", "evidence"]:
        store.write(name, getattr(data, name))
    change = tmp_path / "change.md"
    change.write_text("# Change\nnameの最大長を128文字から256文字へ変更", encoding="utf-8")
    return store, change


def test_cli_provider_and_application_share_kernel(tmp_path):
    store, change = workspace(tmp_path)
    first = analyze_change(store, change, no_llm=True)
    second = analyze_change_llm_first(store, change, no_llm=True)
    repo = AnalysisRepository(store.root)
    assert repo.load(first.run_id)[2] == repo.load(second.run_id)[2]
    project = project_from_path(tmp_path)
    third = execute(project, "analyze", {"path": str(change), "no_llm": True})
    assert repo.load(third["result"]["run_id"])[2] == repo.load(first.run_id)[2]
    summary = report_data(project)["specification_analysis"]
    assert summary["cases"][0]["outcome"] == "inconsistency"
    assert first.impacts[0].review_priority == "must_review"


def test_new_cli_commands_and_immutable_review_history(tmp_path, monkeypatch):
    store, change = workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    assert runner.invoke(app, ["analyze", str(change), "--no-llm"]).exit_code == 0
    shown = runner.invoke(app, ["analysis", "show"])
    assert shown.exit_code == 0, shown.output
    result = json.loads(shown.output)
    assert runner.invoke(app, ["analysis", "replay"]).exit_code == 0
    exported = tmp_path / "snapshot.json"
    assert runner.invoke(app, ["analysis", "export", str(exported)]).exit_code == 0
    assert runner.invoke(app, ["analysis", "import", str(exported)]).exit_code == 0
    decision = runner.invoke(
        app,
        [
            "analysis",
            "decide",
            result["cases"][0]["case_id"],
            "accepted",
            "--actor",
            "tester",
            "--reason",
            "Read original",
        ],
    )
    assert decision.exit_code == 0, decision.output
    assert AnalysisRepository(store.root).decisions(result["analysis_id"])[0].actor == "tester"
    invalid = runner.invoke(app, ["analysis", "replay", "missing"])
    assert invalid.exit_code != 0


def test_legacy_review_flags_changed_preconditions_without_changing_human_status(tmp_path):
    store, change = workspace(tmp_path)
    first = analyze_change_llm_first(store, change, no_llm=True)
    decision = store.read("impact_decisions", ImpactDecision)[0]
    set_impact_status(store, decision.impact_id, "accepted", "Read original")
    assert (
        len(
            AnalysisRepository(store.root).decisions(
                AnalysisRepository(store.root).load(first.run_id)[2].analysis_id
            )
        )
        == 1
    )
    change.write_text("# Change\nnameの最大長を128文字から512文字へ変更", encoding="utf-8")
    analyze_change_llm_first(store, change, no_llm=True)
    updated = store.read("impact_decisions", ImpactDecision)[0]
    assert updated.status == "accepted"
    assert updated.needs_revalidation
    assert updated == ImpactDecision.model_validate_json(updated.model_dump_json())


def local_host(tmp_path):
    store, change = workspace(tmp_path)
    atoms = parse_change_atoms(store, change)
    project = project_from_path(tmp_path)
    host = HostWorkflow(
        project,
        HostContext(
            host="test", workspace_root=str(tmp_path), project_id=project.project_id, external=False
        ),
    )
    host._upsert_session(
        change_id=atoms.change_id,
        title="Change",
        change_path=str(change),
        status="atoms_ready",
        atom_ids=[a.atom_id for a in atoms.change_atoms],
    )
    return host, atoms


def payload(atoms, candidate):
    return {
        "change_id": atoms.change_id,
        "hypotheses": [
            {
                "candidate_node_id": candidate["candidate_node_id"],
                "atom_id": candidate["atom_id"],
                "impact_type": "constraint_change",
                "required_actions": ["Review original"],
                "reason": "Check typed length",
                "evidence_ids": candidate["evidence_ids"],
            }
        ],
    }


def test_host_rejects_stale_context_and_cross_operation_attribution(tmp_path):
    host, atoms = local_host(tmp_path)
    prepared = host.prepare_impact_context(atoms.change_id)
    candidate = prepared.payload["candidates"][0]
    submitted = payload(atoms, candidate)
    submitted["hypotheses"][0]["atom_id"] = "other-operation"
    with pytest.raises(ValueError, match="candidate|atom"):
        host.submit_impact_hypotheses(prepared.context_id, submitted, "bad-atom")
    from specimpact.models import Evidence

    evidence = host.store.read("evidence", Evidence)
    evidence[0].quote = "name maxLength: 999 characters"
    host.store.write("evidence", evidence)
    with pytest.raises(ValueError, match="stale"):
        host.submit_impact_hypotheses(prepared.context_id, payload(atoms, candidate), "stale")


def test_host_pages_bind_each_candidate_to_its_own_operation(tmp_path):
    host, atoms = local_host(tmp_path)
    second = atoms.change_atoms[0].model_copy(update={"atom_id": "second"})
    host.store.write("change_atoms", [*atoms.change_atoms, second])
    first = host.prepare_impact_context(atoms.change_id, limit=1)
    next_page = host.prepare_impact_context(atoms.change_id, offset=1, limit=1)
    assert first.payload["candidate_page"]["next_offset"] == 1
    assert first.payload["candidate_page"]["partial"]
    assert next_page.payload["candidate_page"]["next_offset"] is None
    assert (
        first.payload["candidates"][0]["atom_id"] != next_page.payload["candidates"][0]["atom_id"]
    )
    with pytest.raises(ValueError, match="offset"):
        host.prepare_impact_context(atoms.change_id, offset=-1)
