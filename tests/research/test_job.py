import logging
import socket
import threading

import pytest

from superbot import research
from superbot.core import scheduler
from superbot.core.config import Settings
from superbot.main import run


@pytest.fixture(autouse=True)
def _stop():
    yield
    scheduler.stop()


def test_no_key_skips_research(engine, caplog):
    caplog.set_level(logging.INFO)
    assert research.register(Settings(anthropic_api_key="sk")) is False
    assert "research skipped: no CJ_API_KEY" in caplog.text
    assert "research.find" not in scheduler.job_ids()


def test_key_schedules_daily_job_at_hour(engine):
    s = Settings(anthropic_api_key="sk", cj_api_key="CJ1@api@x", research_hour=7)
    assert research.register(s) is True
    scheduler.start(s)
    job = next(j for j in scheduler._sched().get_jobs() if j.id == "research.find")
    assert "hour='7'" in str(job.trigger) and "minute='0'" in str(job.trigger)


def test_cj_key_is_masked_in_log(engine, db_url, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("CJ_API_KEY", "CJ999@api@topsecret")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        monkeypatch.setenv("DASHBOARD_PORT", str(s.getsockname()[1]))
    stop = threading.Event()
    stop.set()
    run([], db_url=db_url, stop=stop)
    logging.getLogger("superbot").info("leak check CJ999@api@topsecret")
    for h in logging.getLogger().handlers:
        h.flush()
    logged = (tmp_path / "data" / "logs" / "superbot.log").read_text(encoding="utf-8")
    assert "research: finds products daily at 09:00" in logged
    assert "topsecret" not in logged
