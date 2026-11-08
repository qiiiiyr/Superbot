from datetime import UTC, datetime

from sqlalchemy import text

from superbot.core import approvals, pause, scheduler
from superbot.core.approvals import executor


def test_status_shows_running(client):
    r = client.get("/status")
    assert r.status_code == 200 and "Running" in r.text


def test_status_shows_paused(client):
    pause.set_paused(True)
    assert "Paused" in client.get("/status").text


def test_root_goes_to_dashboard(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (200, 307)


@executor("test.dash_thing")
def _thing(payload: dict) -> dict:
    return {}


def test_approvals_page_lists_pending_with_details_and_expiry(client):
    title = "Order #1042: 2× lamp ($18.40)"
    approvals.propose("test.dash_thing", title, {"order": 1042, "items": ["lamp"]})
    page = client.get("/").text
    assert "Order #1042: 2× lamp ($18.40)" in page
    assert "order" in page and "1042" in page and "[&#34;lamp&#34;]" in page
    assert "expires in 47h" in page or "expires in 48h" in page


def test_empty_queue_says_so(client):
    assert "Nothing is waiting for you" in client.get("/").text


def test_html_in_title_and_payload_is_shown_as_text(client):
    approvals.propose("test.dash_thing", "<script>alert(1)</script>", {"<b>k</b>": "<img src=x>"})
    page = client.get("/").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
    assert "<img src=x>" not in page and "<b>k</b>" not in page


@executor("test.dash_ok")
def _ok(payload: dict) -> dict:
    return {"cj_order_id": "CJ-77"}


@executor("test.dash_fail")
def _fail(payload: dict) -> dict:
    raise RuntimeError("out of stock")


def test_history_shows_results_errors_and_interrupted(client, engine):
    for kind in ("test.dash_ok", "test.dash_fail"):
        approvals.approve(approvals.propose(kind, kind, {}))
    approvals.run_approved()
    stuck = approvals.propose("test.dash_ok", "stuck one", {})
    approvals.approve(stuck)
    with engine.begin() as c:
        c.execute(text("UPDATE actions SET status='executing' WHERE id=:i"), {"i": stuck})
    approvals.recover_interrupted()

    page = client.get("/history").text
    assert "CJ-77" in page and "out of stock" in page
    assert 'class="interrupted"' in page and "check manually" in page
    assert page.index("stuck one") < page.index("test.dash_ok")  # newest first


def test_empty_history(client):
    assert "Nothing has happened yet" in client.get("/history").text


def test_status_shows_spend_against_cap(client, engine):
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO llm_usage (at, model, input_tokens, output_tokens, cost_cents)"
                " VALUES (:t, 'x', 0, 0, 37)"
            ),
            {"t": datetime.now(UTC).isoformat()},
        )
    assert "$0.37 of $5.00 this month" in client.get("/status").text


def test_status_shows_job_last_run(client):
    page = client.get("/status").text
    assert "Run approved actions" in page and "not yet" in page
    scheduler.guarded(lambda: None, "core.run_approved")()
    assert "Run approved actions</td><td>20" in client.get("/status").text


def test_forced_pause_is_explained_and_resume_refused(client, post):
    pause.force(True)
    try:
        assert "PAUSED=true" in client.get("/status").text
        r = post("/resume")
        assert r.headers["location"] == "/status?done=forced" and pause.is_paused()
    finally:
        pause.force(False)


def test_nav_marks_current_page_and_stylesheet_loads(client):
    page = client.get("/history").text
    assert '<a href="/history" aria-current="page">History</a>' in page
    assert client.get("/static/style.css").status_code == 200
