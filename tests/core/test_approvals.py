from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from superbot.core import approvals, db
from superbot.core.approvals import ApprovalError, executor


@executor("test.do_thing")
def _do_thing(payload: dict) -> dict:
    return {"echo": payload}


def _audit_events(engine, action_id):
    with engine.connect() as c:
        rows = c.execute(
            text("SELECT event, actor FROM audit_log WHERE action_id=:i ORDER BY id"),
            {"i": action_id},
        )
        return [tuple(r) for r in rows]


def test_propose_stores_pending_and_survives_restart(engine, db_url):
    aid = approvals.propose("test.do_thing", "Do it", {"n": 1})
    db.use(db_url)  # fresh engine = simulated restart
    [item] = approvals.list_pending()
    assert (item["id"], item["status"], item["payload"]) == (aid, "pending", {"n": 1})
    assert _audit_events(engine, aid) == [("proposed", "test")]


def test_unknown_kind_is_refused(engine):
    with pytest.raises(ApprovalError, match="no executor"):
        approvals.propose("test.nope", "x", {})
    assert approvals.list_pending() == []


@pytest.mark.parametrize(
    "decide, status", [(approvals.approve, "approved"), (approvals.reject, "rejected")]
)
def test_decide_pending(engine, decide, status):
    aid = approvals.propose("test.do_thing", "x", {})
    decide(aid)
    item = approvals.get(aid)
    assert item["status"] == status and item["decided_at"]
    assert _audit_events(engine, aid)[-1] == (status, "owner")


def test_only_pending_can_be_decided(engine):
    aid = approvals.propose("test.do_thing", "x", {})
    approvals.reject(aid)
    for decide in (approvals.approve, approvals.reject):
        with pytest.raises(ApprovalError, match="not pending"):
            decide(aid)
    with pytest.raises(ApprovalError, match="not pending"):
        approvals.approve(9999)
    assert approvals.get(aid)["status"] == "rejected"


def test_expire_old(engine):
    old = approvals.propose("test.do_thing", "old", {})
    new = approvals.propose("test.do_thing", "new", {})
    past = (datetime.now(UTC) - timedelta(hours=49)).isoformat()
    with engine.begin() as c:
        c.execute(text("UPDATE actions SET created_at=:t WHERE id=:i"), {"t": past, "i": old})
    assert approvals.expire_old(hours=48) == 1
    assert approvals.get(old)["status"] == "expired"
    assert approvals.get(new)["status"] == "pending"
    assert _audit_events(engine, old)[-1] == ("expired", "system")


def test_list_recent_newest_first_skips_pending_and_limits(engine):
    ids = [approvals.propose("test.do_thing", f"a{i}", {}) for i in range(4)]
    for aid in ids[:3]:
        approvals.reject(aid)
    recent = approvals.list_recent(limit=2)
    assert [r["id"] for r in recent] == [ids[2], ids[1]]
    assert all(r["status"] != "pending" for r in approvals.list_recent())
