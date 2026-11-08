# Implementation Plan: dashboard

Spec: [SPEC-dashboard.md](../SPEC-dashboard.md) · Tasks: [todo-dashboard.md](todo-dashboard.md) · Core plan (done): [plan.md](plan.md)

## Overview

This adds a FastAPI page to the running bot, served on `127.0.0.1:8000`, built in vertical slices. Each task ships one page or button end to end (route, template, test), so the bot stays usable after every task. The security checks come first because every later button depends on them.

## Architecture Decisions

- **One process.** `main.run()` starts uvicorn in a background thread, and the main thread keeps its existing `while not stop.wait(1)` loop. On exit it sets `server.should_exit` and joins the thread, then stops the scheduler. This keeps Ctrl+C working on Windows and keeps the existing `stop` event test pattern. Check during Task 1 that uvicorn skips installing signal handlers outside the main thread; if it doesn't, run uvicorn in the main thread and drop the loop instead.
- **`create_app(port)` factory** in `dashboard/app.py`, so tests build an app with `TestClient` and no real port.
- **Messages after a click use fixed codes** (`/?done=approved`) mapped to text on the server. No user text goes in URLs, so nobody can craft a link that shows a fake "Approved" message.
- **CSRF token:** one random token per process (`secrets.token_urlsafe`), put in every form and checked with `secrets.compare_digest`. Together with the Host and Origin checks, that covers a localhost-only app. Per-session tokens come with the login work before the cloud move.
- **Job last-run times** are kept in memory by `scheduler.guarded()` (a dict of job id to UTC time). They don't survive a restart, which is fine since the jobs run every 30s or hourly. No schema change.
- **`approvals.list_recent(limit)`** is added to `core` and reads the same `actions` table. No schema change.
- **Dependencies:** `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, plus `httpx` as a dev dependency, added with `uv add` in Task 1 and pinned in `uv.lock`. Check usage against the FastAPI and uvicorn docs at that point.

## Task List

### Phase 1: Served and safe
- [ ] Task 1: Dashboard served by `uv run superbot`, with a status page showing running or paused
- [ ] Task 2: Pause/Resume button behind the Host, Origin and CSRF checks

### Checkpoint D
- [ ] Tests and ruff clean; open the page in a real browser and pause and resume from it
- [ ] Security tests: foreign Host, foreign Origin, missing or wrong token are all refused

### Phase 2: The pages you use daily
- [ ] Task 3: Approvals page with Approve and Reject
- [ ] Task 4: History page
- [ ] Task 5: Status page details (AI spend, forced pause, job last-run times)

### Checkpoint E
- [ ] Propose a test action by hand, approve it in the browser, and see it in history

### Phase 3: Finish
- [ ] Task 6: Logs page
- [ ] Task 7: Stylesheet, keyboard and narrow-screen pass, setup guide update

### Checkpoint F
- [ ] All 10 dashboard success criteria met; owner review → start `SPEC-research.md`

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A malicious website posts to `localhost:8000` | High: it could approve an order | Task 2 lands the Host, Origin and CSRF checks before any other button exists, with a test for each |
| uvicorn in a thread breaks Ctrl+C on Windows | Medium | Checked by hand in Task 1; fallback described above |
| AI- or supplier-written text injects HTML | Medium | Autoescape on, plus a `<script>` test in Task 3 |
| Approving from a stale page acts on an item that already expired | Low | `core` already refuses non-pending items; the page shows the message |
| Port 8000 already in use | Low | `DASHBOARD_PORT` setting; a clear one-line error at start-up |

## Open Questions

None. The spec decisions are resolved.
