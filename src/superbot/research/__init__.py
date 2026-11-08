"""Finds products on CJ and suggests the profitable ones for approval."""

import logging
from functools import partial

from superbot.core import scheduler
from superbot.core.config import Settings
from superbot.research import finder  # also registers the research.shortlist executor
from superbot.research.cj import CJClient

log = logging.getLogger("superbot.research")


def register(settings: Settings) -> bool:
    key = settings.cj_api_key.get_secret_value()
    if not key:
        log.info("research skipped: no CJ_API_KEY")
        return False
    scheduler.add_job(
        partial(finder.run, CJClient(key), settings),
        job_id="research.find",
        hour=settings.research_hour,
    )
    log.info("research: finds products daily at %02d:00", settings.research_hour)
    return True
