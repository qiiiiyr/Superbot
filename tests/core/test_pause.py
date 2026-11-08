import pytest

from superbot.core import approvals, pause
from superbot.core.approvals import executor

ran: list[dict] = []


@executor("test.pausable")
def _run(payload: dict) -> dict:
    ran.append(payload)
    return {}


@pytest.fixture(autouse=True)
def _reset():
    ran.clear()
    yield
    pause.force(False)


def test_paused_queue_records_decisions_but_runs_nothing(engine):
    pause.set_paused(True)
    aid = approvals.propose("test.pausable", "x", {})
    approvals.approve(aid)
    assert approvals.run_approved() == 0 and ran == []
    assert approvals.get(aid)["status"] == "approved"
    pause.set_paused(False)
    assert approvals.run_approved() == 1 and len(ran) == 1


def test_env_force_overrides_db_flag(engine):
    pause.set_paused(False)
    pause.force(True)
    assert pause.is_paused()


def test_cli_pause_and_resume(engine, db_url, capsys):
    from superbot.main import run

    run(["pause"], db_url=db_url)
    assert pause.is_paused() and "paused" in capsys.readouterr().out
    run(["resume"], db_url=db_url)
    assert not pause.is_paused() and "running" in capsys.readouterr().out


@executor("test.pauses_mid_batch")
def _pauses(payload: dict) -> dict:
    ran.append(payload)
    pause.set_paused(True)  # owner hits Pause while the batch is running
    return {}


def test_pause_mid_batch_stops_the_rest(engine):
    pause.set_paused(False)
    first = approvals.propose("test.pauses_mid_batch", "x", {})
    second = approvals.propose("test.pausable", "y", {})
    approvals.approve(first)
    approvals.approve(second)
    assert approvals.run_approved() == 1
    assert approvals.get(second)["status"] == "approved"
    pause.set_paused(False)
