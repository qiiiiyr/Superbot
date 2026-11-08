import logging
import sys
import threading
import time

import uvicorn

from superbot import research
from superbot.core import approvals, db, llm, pause, scheduler
from superbot.core.config import Settings, load_settings
from superbot.core.log import setup_logging
from superbot.dashboard.app import create_app

log = logging.getLogger("superbot")


def _run_quietly(server: uvicorn.Server) -> None:
    try:
        server.run()
    except SystemExit:  # bind failed; uvicorn logged why and _serve reports it in one line
        pass


def _serve(settings: Settings) -> tuple[uvicorn.Server, threading.Thread]:
    # log_config=None sends uvicorn's logs through our handlers, so keys stay masked
    config = uvicorn.Config(
        create_app(settings), host="127.0.0.1", port=settings.dashboard_port, log_config=None
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=_run_quietly, args=(server,), name="dashboard", daemon=True)
    thread.start()
    while not server.started and thread.is_alive():
        time.sleep(0.05)
    if not server.started:
        raise SystemExit(
            f"Port {settings.dashboard_port} is already in use — "
            "set DASHBOARD_PORT in .env to another number"
        )
    return server, thread


def run(
    argv: list[str] | None = None,
    db_url: str = db.DEFAULT_URL,
    stop: threading.Event | None = None,
) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("pause", "resume"):
        # works without an API key so the owner can always stop the bot
        db.migrate(db_url)
        db.use(db_url)
        pause.set_paused(argv[0] == "pause")
        print("superbot is now", "paused" if argv[0] == "pause" else "running")
        return
    settings = load_settings()
    setup_logging(
        secrets=[
            settings.anthropic_api_key.get_secret_value(),
            settings.cj_api_key.get_secret_value(),
        ]
    )
    db.migrate(db_url)
    db.use(db_url)
    pause.force(settings.paused)
    llm.configure(settings)
    # port bind doubles as a single-instance lock: a second copy exits here
    server, thread = _serve(settings)
    if n := approvals.recover_interrupted():
        log.warning("%d action(s) were cut off mid-run and marked failed — check them manually", n)
    scheduler.start(settings)
    research.register(settings)
    log.info(
        "ready%s — open http://127.0.0.1:%d",
        " (paused)" if pause.is_paused() else "",
        settings.dashboard_port,
    )
    stop = stop or threading.Event()
    try:
        while not stop.wait(1):  # short waits keep Ctrl+C responsive on Windows
            pass
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        server.should_exit = True
        thread.join(timeout=10)
        log.info("stopped")
        logging.shutdown()
