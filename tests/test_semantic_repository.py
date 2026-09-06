import sqlite3

import pytest
from test_semantic_kernel import source

from specimpact.application.security import ProjectWriteLock
from specimpact.semantic.repository import AnalysisRepository, DecisionEvent


def test_snapshot_replay_export_import_and_old_versions(tmp_path):
    repo = AnalysisRepository(tmp_path)
    original = source()
    result = repo.save(original, report_id="report-1")
    assert repo.replay("report-1") == result
    original.evidence[0].quote = "name maxLength: 512 characters"
    changed = repo.save(original, report_id="report-2")
    assert changed.analysis_id != result.analysis_id
    assert repo.replay("report-1") == result
    target = AnalysisRepository(tmp_path / "import")
    assert target.import_snapshot(repo.export("report-1")) == result
    assert target.replay(result.analysis_id) == result
    with pytest.raises(ValueError, match="immutable"):
        repo.save(original, report_id="report-1")


def test_transaction_rolls_back_snapshot_and_result(tmp_path, monkeypatch):
    repo = AnalysisRepository(tmp_path)

    def fail(*args):
        raise RuntimeError("injected failure between snapshot and run")

    monkeypatch.setattr(repo, "_insert_result", fail)
    with pytest.raises(RuntimeError, match="injected"):
        repo.save(source())
    with sqlite3.connect(repo.path) as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM runs").fetchone()[0] == 0


def test_tampering_detected_on_load(tmp_path):
    repo = AnalysisRepository(tmp_path)
    result = repo.save(source())
    with sqlite3.connect(repo.path) as db:
        db.execute("UPDATE snapshots SET payload=replace(payload, 'source-v1', 'source-v2')")
    with pytest.raises(ValueError, match="integrity"):
        repo.replay(result.analysis_id)


def test_decisions_are_immutable_and_snapshot_bound(tmp_path):
    repo = AnalysisRepository(tmp_path)
    data = source()
    first = repo.save(data)
    event = DecisionEvent(
        analysis_id=first.analysis_id,
        case_id=first.cases[0].case_id,
        actor="reviewer",
        status="accepted",
        reason="Checked original",
    )
    assert DecisionEvent.model_validate_json(event.model_dump_json()) == event
    repo.decide(event)
    repo.decide(event)
    assert repo.decisions(first.analysis_id) == [event]
    with pytest.raises(ValueError, match="immutable"):
        repo.decide(event.model_copy(update={"reason": "rewritten"}))
    data.operations[0].after.value = 64
    second = repo.save(data)
    assert repo.decisions(second.analysis_id) == []
    assert repo.decisions(first.analysis_id) == [event]


def test_nested_lock_does_not_unlock_outer_transaction(tmp_path):
    with ProjectWriteLock(tmp_path):
        with ProjectWriteLock(tmp_path):
            assert (tmp_path / "write.lock").exists()
        assert (tmp_path / "write.lock").exists()
