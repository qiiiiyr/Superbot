from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from superbot.core import approvals, pause
from superbot.core.approvals import executor


def test_pause_then_resume(client, post):
    r = post("/pause")
    assert r.status_code == 303 and r.headers["location"] == "/status?done=paused"
    assert pause.is_paused()
    page = client.get(r.headers["location"]).text
    assert "Paused" in page and "Nothing will run until you resume" in page

    r = post("/resume")
    assert not pause.is_paused()
    assert "Running" in client.get(r.headers["location"]).text


def test_unknown_message_code_shows_nothing(client):
    page = client.get("/status?done=<b>Approved!</b>").text
    assert "Approved!" not in page


@executor("test.dash_act")
def _act(payload: dict) -> dict:
    return {}


@pytest.mark.parametrize("verb, status", [("approve", "approved"), ("reject", "rejected")])
def test_decide_from_page(client, post, verb, status):
    aid = approvals.propose("test.dash_act", "x", {})
    r = post(f"/actions/{aid}/{verb}")
    assert r.headers["location"] == f"/?done={status}"
    assert approvals.get(aid)["status"] == status
    assert "x" not in [i["title"] for i in approvals.list_pending()]


def test_second_click_changes_nothing(client, post):
    aid = approvals.propose("test.dash_act", "x", {})
    post(f"/actions/{aid}/approve")
    r = post(f"/actions/{aid}/reject")
    assert r.headers["location"] == "/?done=not_pending"
    assert approvals.get(aid)["status"] == "approved"
    assert "already decided or has expired" in client.get(r.headers["location"]).text


def test_cannot_approve_item_past_expiry(engine, post):
    aid = approvals.propose("test.dash_act", "old", {})
    past = (datetime.now(UTC) - timedelta(hours=49)).isoformat()
    with engine.begin() as c:
        c.execute(text("UPDATE actions SET created_at=:t WHERE id=:i"), {"t": past, "i": aid})
    assert post(f"/actions/{aid}/approve").headers["location"] == "/?done=not_pending"
    assert approvals.get(aid)["status"] == "expired"


def test_decide_needs_csrf(client):
    aid = approvals.propose("test.dash_act", "x", {})
    r = client.post(f"/actions/{aid}/approve", headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 403 and approvals.get(aid)["status"] == "pending"
