from test_semantic_integration import local_host, payload

from specimpact.application.host_workflow import HostWorkflow
from specimpact.semantic.repository import AnalysisRepository


def test_host_submission_uses_the_same_kernel_as_local_and_pages_survive_restart(tmp_path):
    host, atoms = local_host(tmp_path)
    second = atoms.change_atoms[0].model_copy(update={"atom_id": "second"})
    host.store.write("change_atoms", [*atoms.change_atoms, second])
    prepared = host.prepare_impact_context(atoms.change_id, limit=1)
    first = prepared.payload["candidates"][0]
    first_result = host.submit_impact_hypotheses(
        prepared.context_id, payload(atoms, first), "page1"
    )
    repo = AnalysisRepository(host.store.root)
    run_id = (host.store.root / "latest_run").read_text()
    analysis = repo.load(run_id)[2]
    assert {case.operation_id for case in analysis.cases} == {first["atom_id"], "second"}
    assert len(first_result.impacts) == 1  # v1 artifact projection; two typed operation cases
    restarted = HostWorkflow(host.project, host.host)
    second_page = restarted.prepare_impact_context(atoms.change_id, offset=1, limit=1)
    restarted.submit_impact_hypotheses(
        second_page.context_id,
        payload(atoms, second_page.payload["candidates"][0]),
        "page2",
    )
    records = restarted._read_jsonl(host.store.root / "host_impact_results.jsonl")
    assert len(records) == 2
    assert repo.load((host.store.root / "latest_run").read_text())[2] == analysis
