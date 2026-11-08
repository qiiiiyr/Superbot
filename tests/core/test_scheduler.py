import logging

import pytest

from superbot.core import pause, scheduler
from superbot.core.config import Settings

ran: list[int] = []


def _job():
    ran.append(1)


def _broken():
    raise RuntimeError("kaboom")


@pytest.fixture(autouse=True)
def _reset():
    ran.clear()
    yield
    scheduler.stop()
    pause.force(False)


def test_guarded_job_skips_while_paused_and_runs_after_resume(engine):
    job = scheduler.guarded(_job, "t")
    pause.set_paused(True)
    job()
    assert ran == []
    pause.set_paused(False)
    job()
    assert ran == [1]


def test_job_error_is_logged_and_scheduler_keeps_running(engine, caplog):
    scheduler.start(Settings(anthropic_api_key="sk-test"))
    with caplog.at_level(logging.ERROR):
        scheduler.guarded(_broken, "broken")()
    assert "broken" in caplog.text and "kaboom" in caplog.text
    assert scheduler.is_running()


def test_start_registers_builtin_jobs(engine):
    scheduler.start(Settings(anthropic_api_key="sk-test"))
    scheduler.start(Settings(anthropic_api_key="sk-test"))  # restart-safe: no duplicates
    assert scheduler.job_ids() == {"core.run_approved", "core.expire_old"}
    scheduler.stop()
    assert not scheduler.is_running()


def test_guarded_records_last_run_only_when_it_runs(engine):
    pause.set_paused(True)
    scheduler.guarded(_job, "t.last")()
    assert "t.last" not in scheduler.last_runs()
    pause.set_paused(False)
    scheduler.guarded(_job, "t.last")()
    assert "t.last" in scheduler.last_runs()
