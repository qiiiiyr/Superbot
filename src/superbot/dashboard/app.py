"""The owner's web page. Routes stay thin: they call core and render a template."""

import json
import secrets
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from superbot.core import approvals, llm, pause, scheduler
from superbot.core.approvals import ApprovalError
from superbot.core.config import Settings

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=HERE / "templates")  # autoescapes .html

# Only these fixed texts can appear after a click, so a crafted link can't show a fake message.
MESSAGES = {
    "paused": "Paused. Nothing will run until you resume.",
    "resumed": "Resumed. Approved actions run within 30 seconds.",
    "approved": "Approved. It runs within 30 seconds unless the bot is paused.",
    "rejected": "Rejected. It will not run.",
    "not_pending": "That action was already decided or has expired, so nothing changed.",
    "forced": "Can't resume from here: PAUSED=true is set in .env. Change it to false and restart.",
}

JOB_NAMES = {"core.run_approved": "Run approved actions", "core.expire_old": "Expire old approvals"}


def dollars(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def expires_in(created_at: str, hours: int) -> str:
    left = datetime.fromisoformat(created_at) + timedelta(hours=hours) - datetime.now(UTC)
    whole = int(left.total_seconds() // 3600)
    return f"expires in {whole}h" if whole >= 1 else "expires in under 1h"


def details(payload: dict) -> list[tuple[str, str]]:
    return [
        (k, v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
        for k, v in payload.items()
    ]


def check_post(request: Request, csrf: str = Form("")) -> None:
    """Every POST must come from this dashboard's own page and carry its token."""
    source = request.headers.get("origin") or request.headers.get("referer") or ""
    if urlsplit(source).netloc != request.headers.get("host"):
        raise HTTPException(403, "Request did not come from the dashboard")
    if not secrets.compare_digest(csrf, request.app.state.csrf):
        raise HTTPException(403, "Form expired — reload the page and try again")


def render(request: Request, name: str, **context):
    context |= {
        "csrf": request.app.state.csrf,
        "msg": MESSAGES.get(request.query_params.get("done")),
    }
    return templates.TemplateResponse(request, name, context)


def done(path: str, code: str) -> RedirectResponse:
    return RedirectResponse(f"{path}?done={code}", status_code=303)  # 303: refresh won't re-POST


def create_app(settings: Settings, log_file: Path = Path("data/logs/superbot.log")) -> FastAPI:
    expiry_hours = settings.approval_expiry_hours
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.csrf = secrets.token_urlsafe(32)
    # Blocks DNS rebinding: a foreign site's name pointed at 127.0.0.1 gets a 400.
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.get("/")
    def queue(request: Request):
        items = [
            {
                **a,
                "details": details(a["payload"]),
                "expires": expires_in(a["created_at"], expiry_hours),
            }
            for a in approvals.list_pending()
        ]
        return render(request, "approvals.html", items=items)

    @app.post("/actions/{action_id}/{verb}", dependencies=[Depends(check_post)])
    def decide(action_id: int, verb: str) -> RedirectResponse:
        if verb not in ("approve", "reject"):
            raise HTTPException(404)
        approvals.expire_old(
            expiry_hours
        )  # a stale page must not approve something already past expiry
        try:
            (approvals.approve if verb == "approve" else approvals.reject)(action_id)
        except ApprovalError:
            return done("/", "not_pending")
        return done("/", "approved" if verb == "approve" else "rejected")

    @app.get("/history")
    def history(request: Request):
        return render(request, "history.html", items=approvals.list_recent(50))

    @app.get("/logs")
    def logs(request: Request):
        try:
            with log_file.open(encoding="utf-8", errors="replace") as f:
                lines = list(deque(f, maxlen=200))  # streams the file, keeps only the tail
        except FileNotFoundError:
            lines = None
        return render(request, "logs.html", lines=lines)

    @app.get("/status")
    def status(request: Request):
        runs = scheduler.last_runs()
        jobs = [
            (
                JOB_NAMES.get(j, j),
                runs[j].strftime("%Y-%m-%d %H:%M UTC") if j in runs else "not yet",
            )
            for j in sorted(set(JOB_NAMES) | set(runs))
        ]
        spend = f"{dollars(llm.month_spend_cents())} of {dollars(settings.monthly_llm_cap_cents)}"
        return render(
            request,
            "status.html",
            paused=pause.is_paused(),
            forced=pause.is_forced(),
            spend=spend + " this month",
            jobs=jobs,
            scheduler_running=scheduler.is_running(),
        )

    @app.post("/pause", dependencies=[Depends(check_post)])
    def do_pause() -> RedirectResponse:
        pause.set_paused(True)
        return done("/status", "paused")

    @app.post("/resume", dependencies=[Depends(check_post)])
    def do_resume() -> RedirectResponse:
        if pause.is_forced():
            return done("/status", "forced")
        pause.set_paused(False)
        return done("/status", "resumed")

    return app
