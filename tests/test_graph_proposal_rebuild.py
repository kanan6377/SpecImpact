from pathlib import Path
from shutil import copy2

from specimpact.dirty_excel.ingestion import decide_graph_proposal, ingest_dirty_excel
from specimpact.llm_graph.schemas import GraphProposal
from specimpact.models import Relation
from specimpact.store import LocalStore


def test_graph_proposal_decision_rebuilds_the_workbook_graph(tmp_path: Path) -> None:
    source = next(Path("examples/dirty_sier_excel/docs").glob("02_*.xlsx"))
    workbook = tmp_path / "api.xlsx"
    copy2(source, workbook)
    store = LocalStore(tmp_path / ".specimpact")
    store.init()
    ingest_dirty_excel(store, workbook)
    proposal = store.read("graph_proposals", GraphProposal)[0]
    initial_count = len(store.read("relations", Relation))
    assert initial_count > 0

    decide_graph_proposal(store, proposal.proposal_id, "rejected")
    assert len(store.read("relations", Relation)) < initial_count

    decide_graph_proposal(store, proposal.proposal_id, "accepted")
    assert len(store.read("relations", Relation)) == initial_count
