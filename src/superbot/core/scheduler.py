"""Background jobs. Every job skips while paused, and one failing job never stops the others."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial

from apscheduler.schedulers.background import BackgroundScheduler

from superbot.core import approvals, pause
from superbot.core.config import Settings

log = logging.getLogger("superbot.scheduler")
_scheduler: BackgroundScheduler | None = None
_last_run: dict[str, datetime] = {}  # in memory only: jobs run every 30s or hourly anyway


def guarded(fn: Callable[[], object], name: str) -> Callable[[], None]:
    def run() -> None:
        try:
            if pause.is_paused():
                log.debug("paused, skipping %s", name)
                return
            _last_run[name] = datetime.now(UTC)
            fn()
        except Exception:
            log.exception("job %s failed", name)

    return run


def add_job(fn: Callable[[], object], *, job_id: str, seconds: int = 0, minutes: int = 0) -> None:
    _sched().add_job(
        guarded(fn, job_id),
        "interval",
        seconds=seconds,
        minutes=minutes,
        id=job_id,
        name=job_id,
        replace_existing=True,
        max_instances=1,  # a slow run never overlaps itself
        coalesce=True,
    )


def _sched() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone=UTC)
    return _scheduler


def start(settings: Settings) -> None:
    add_job(approvals.run_approved, job_id="core.run_approved", seconds=30)
    add_job(
        partial(approvals.expire_old, settings.approval_expiry_hours),
        job_id="core.expire_old",
        minutes=60,
    )
    if not _sched().running:
        _sched().start()


def stop() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=True)
    _scheduler = None


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running


def job_ids() -> set[str]:
    return {j.id for j in _sched().get_jobs()}


def last_runs() -> dict[str, datetime]:
    return dict(_last_run)
