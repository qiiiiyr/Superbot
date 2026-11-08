import socket
import threading

import pytest
from sqlalchemy import text

from superbot.core import approvals, scheduler
from superbot.core.approvals import executor
from superbot.main import run


@executor("test.main_stuck")
def _stuck(payload: dict) -> dict:
    return {}


def test_run_reaches_ready_recovers_and_stops(engine, db_url, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")
    monkeypatch.setenv("DASHBOARD_PORT", str(_free_port()))
    aid = approvals.propose("test.main_stuck", "x", {})
    approvals.approve(aid)
    with engine.begin() as c:
        c.execute(text("UPDATE actions SET status='executing' WHERE id=:i"), {"i": aid})

    stop = threading.Event()
    stop.set()  # return right after start-up
    run([], db_url=db_url, stop=stop)

    logged = (tmp_path / "data" / "logs" / "superbot.log").read_text(encoding="utf-8")
    assert "ready — open http://127.0.0.1:" in logged and "stopped" in logged
    assert "1 action(s) were cut off" in logged
    assert "sk-secret-123" not in logged
    assert approvals.get(aid)["status"] == "failed"
    assert not scheduler.is_running()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_in_use_gives_one_line_error(engine, db_url, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    aid = approvals.propose("test.main_stuck", "x", {})
    approvals.approve(aid)
    with engine.begin() as c:  # the first bot is running this right now
        c.execute(text("UPDATE actions SET status='executing' WHERE id=:i"), {"i": aid})
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        monkeypatch.setenv("DASHBOARD_PORT", str(busy.getsockname()[1]))
        with pytest.raises(SystemExit, match="DASHBOARD_PORT"):
            run([], db_url=db_url, stop=threading.Event())
    assert not scheduler.is_running()
    assert approvals.get(aid)["status"] == "executing"  # second start must not touch it
