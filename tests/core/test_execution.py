import threading
import time

import pytest
from sqlalchemy import text

from superbot.core import approvals, db
from superbot.core.approvals import executor

calls: list[dict] = []


class Crash(BaseException):
    """Stands in for the process dying mid-run (not caught like a normal error)."""


@executor("test.slow")
def _slow(payload: dict) -> dict:
    calls.append(payload)
    time.sleep(0.2)  # keep the race window open
    return {"ok": True}


@executor("test.boom")
def _boom(payload: dict) -> dict:
    calls.append(payload)
    raise RuntimeError("supplier said no")


@executor("test.crash")
def _crash(payload: dict) -> dict:
    raise Crash


@pytest.fixture(autouse=True)
def _reset():
    calls.clear()


def _approved(kind: str) -> int:
    aid = approvals.propose(kind, "x", {"k": kind})
    approvals.approve(aid)
    return aid


def test_success_runs_once_and_stores_result(engine):
    aid = _approved("test.slow")
    assert approvals.run_approved() == 1
    assert approvals.run_approved() == 0
    item = approvals.get(aid)
    assert (item["status"], item["result"]) == ("executed", {"ok": True}) and item["executed_at"]
    assert len(calls) == 1


def test_two_threads_run_executor_once(engine):
    aid = _approved("test.slow")
    threads = [threading.Thread(target=approvals.run_approved) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert approvals.get(aid)["status"] == "executed"


def test_error_marks_failed_and_never_retries(engine):
    aid = _approved("test.boom")
    approvals.run_approved()
    approvals.run_approved()
    item = approvals.get(aid)
    assert item["status"] == "failed" and "supplier said no" in item["error"]
    assert len(calls) == 1


def test_pending_rejected_expired_never_run(engine):
    approvals.propose("test.slow", "pending", {})
    approvals.reject(approvals.propose("test.slow", "rejected", {}))
    gone = approvals.propose("test.slow", "expired", {})
    with db.engine().begin() as c:
        c.execute(
            text("UPDATE actions SET created_at='2000-01-01T00:00:00+00:00' WHERE id=:i"),
            {"i": gone},
        )
    approvals.expire_old(hours=48)
    assert approvals.run_approved() == 0
    assert calls == []


def test_crash_mid_run_is_marked_failed_on_restart(engine, db_url):
    aid = _approved("test.crash")
    with pytest.raises(Crash):
        approvals.run_approved()
    assert approvals.get(aid)["status"] == "executing"
    db.use(db_url)  # restart
    assert approvals.recover_interrupted() == 1
    item = approvals.get(aid)
    assert item["status"] == "failed" and item["error"] == "interrupted — check manually"
    assert approvals.run_approved() == 0


@executor("test.datetime_result")
def _datetime_result(payload: dict) -> dict:
    from datetime import UTC, datetime

    return {"placed_at": datetime(2026, 1, 2, tzinfo=UTC)}


def test_result_json_cannot_encode_is_still_saved(engine):
    aid = _approved("test.datetime_result")
    assert approvals.run_approved() == 1
    item = approvals.get(aid)
    assert item["status"] == "executed"
    assert item["result"] == {"placed_at": "2026-01-02 00:00:00+00:00"}
