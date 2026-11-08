# Tasks: dashboard

Plan: [plan-dashboard.md](plan-dashboard.md) · Spec: [SPEC-dashboard.md](../SPEC-dashboard.md)

A task counts as done only when `uv run pytest` passes and `uv run ruff check .` is clean.

---

## Task 1: Dashboard served by the bot

**Description:** Add the dependencies, `create_app(port)`, a base template, and a status page that says "Running" or "Paused". `main.run()` serves it on `127.0.0.1:DASHBOARD_PORT` alongside the scheduler. Requests with a foreign `Host` get a 400.

**Acceptance criteria:**
- [x] `uv run superbot` logs `ready — open http://127.0.0.1:8000`, and `GET /status` shows Running or Paused
- [x] Ctrl+C stops the dashboard and the scheduler; port in use → one-line error naming `DASHBOARD_PORT`
- [x] A request with `Host: evil.example` gets a 400

**Verification:**
- [x] Tests: `TestClient` status page (running and paused); foreign Host → 400; `test_main` still passes with the server started and stopped
- [ ] Manual: open the page in a browser (done), then Ctrl+C in PowerShell exits cleanly (not checked: can't send Ctrl+C from here)

**Dependencies:** core done

**Files:** `pyproject.toml`, `src/superbot/core/config.py` (`dashboard_port`), `src/superbot/dashboard/app.py`, `templates/base.html` + `status.html`, `src/superbot/main.py`, `tests/dashboard/test_pages.py`

**Size:** M

---

## Task 2: Pause/Resume button behind the security checks

**Description:** POST `/pause` and `/resume` call `core.pause`, then redirect with a fixed message code. Every POST checks `Origin` (or `Referer`) and the CSRF token.

**Acceptance criteria:**
- [x] The button pauses or resumes, and the page shows the new state with a message
- [x] A foreign Origin, or a missing or wrong token, gets a 403 and nothing changes
- [x] Message text comes only from fixed codes; an unknown code shows nothing

**Verification:**
- [x] Tests: `tests/dashboard/test_security.py` (each refusal leaves pause unchanged) and `test_actions.py` (pause → resume)

**Dependencies:** Task 1

**Files:** `src/superbot/dashboard/app.py`, `templates/status.html`, `tests/dashboard/test_actions.py`, `tests/dashboard/test_security.py`

**Size:** S

### Checkpoint D
- [x] pytest and ruff clean
- [x] Real browser: pause and resume from the page
- [ ] Review with the owner (deferred, owner AFK)

Checkpoint D results (2026-11-09): 49 tests pass, ruff clean. Installed fastapi 0.162.2, uvicorn 0.54.0, starlette 1.10.0, jinja2 3.1.6, python-multipart 0.0.33, httpx 0.28.1 (dev). Checked in the installed source: uvicorn skips signal handlers off the main thread, Starlette's templates autoescape `.html`, and TrustedHostMiddleware ignores the port. Real browser: the page loads, Pause → Paused with message, Resume → Running. A foreign Host gets a 400. Ready in 5.3s. Port in use → one-line error. Not checked: a real Ctrl+C.

---

## Task 3: Approvals page

**Description:** `GET /` lists pending actions (title, a details table built from the payload, time until expiry), each with Approve and Reject buttons.

**Acceptance criteria:**
- [x] Each pending action shows its title, details and "expires in Xh"; an empty queue says so
- [x] Approve and Reject go through `core` with a confirmation message; a second click shows "already decided" and changes nothing
- [x] `<script>` in a title or payload shows up as text

**Verification:**
- [x] Tests: list, approve, reject, double-approve, expired item, escaping

**Dependencies:** Task 2

**Files:** `src/superbot/dashboard/app.py`, `templates/approvals.html`, `tests/dashboard/test_pages.py`, `tests/dashboard/test_actions.py`

**Size:** M

---

## Task 4: History page

**Description:** Add `approvals.list_recent(limit=50)` to core (everything that isn't pending, newest first), and `GET /history` shows it with the status, result or error. "Interrupted — check manually" rows are highlighted.

**Acceptance criteria:**
- [x] Shows up to 50 items, newest first, with the result or error text
- [x] Interrupted items have a visible highlight and the words "check manually"

**Verification:**
- [x] Tests: `list_recent` order and limit (in `tests/core/test_approvals.py`); page shows executed, failed and interrupted rows

**Dependencies:** Task 3

**Files:** `src/superbot/core/approvals.py`, `src/superbot/dashboard/app.py`, `templates/history.html`, tests

**Size:** S

---

## Task 5: Status page details

**Description:** `scheduler.guarded()` records each job's last run time. The status page adds this month's AI spend against the cap in dollars, whether `.env` forces the pause (if so, the Resume button explains it can't override), and each job's last run.

**Acceptance criteria:**
- [x] Spend shows as `$0.37 of $5.00 this month`, from `llm.month_spend_cents()`
- [x] Forced pause is shown, and Resume explains that `.env` needs changing
- [x] Each built-in job shows a last-run time, or "not yet"

**Verification:**
- [x] Tests: spend formatting, forced-pause text, last-run recorded by `guarded()` (in `tests/core/test_scheduler.py`)

**Dependencies:** Task 2

**Files:** `src/superbot/core/scheduler.py`, `src/superbot/dashboard/app.py`, `templates/status.html`, tests

**Size:** S

### Checkpoint E
- [x] pytest and ruff clean
- [x] Real browser: propose a test action by hand, approve it, and see it executed in history
- [ ] Review with the owner (deferred, owner AFK)

Checkpoint E results (2026-11-09): 64 tests pass, ruff clean. Real browser with a demo bot on a throwaway DB: two actions listed with details and `expires in 47h`. A `<script>` title showed as text and nothing ran. Approve → message → the background job executed it within 30s → history shows `executed` and `{"said": "hello owner"}`; Reject → `rejected`. Status shows `$0.00 of $5.00 this month` and the job's last run. Also: approving refreshes expiry first, so a stale page can't approve something already past 48h. `create_app` now takes `Settings`. Note: the hourly expiry job first runs an hour after start-up.

---

## Task 6: Logs page

**Description:** `GET /logs` shows the last 200 lines of `data/logs/superbot.log`, read from the end of the file without loading it all.

**Acceptance criteria:**
- [x] Shows at most 200 lines, newest last; a missing file shows "no log yet"
- [x] No API key appears (the test logs the key through `core` logging, then loads the page)

**Verification:**
- [x] Tests: 250-line file → 200 shown; missing file; key masked

**Dependencies:** Task 1

**Files:** `src/superbot/dashboard/app.py`, `templates/logs.html`, `tests/dashboard/test_pages.py`

**Size:** S

---

## Task 7: Finish

**Description:** One small stylesheet, navigation between the four pages, and a keyboard and narrow-screen pass. Update `docs/setup.md` with "open the dashboard".

**Acceptance criteria:**
- [x] Every button and link can be reached and used with Tab and Enter, with a visible focus outline
- [x] Readable at 1280px and 375px wide with no sideways scrolling
- [x] Dashboard coverage is at least 90%; ruff is clean

**Verification:**
- [x] Manual: check each page in the browser at both widths using only the keyboard
- [x] `uv run pytest --cov=superbot` shows dashboard coverage of at least 90%

**Dependencies:** Tasks 3–6

**Files:** `src/superbot/dashboard/static/style.css`, `templates/base.html`, `docs/setup.md`

**Size:** S

### Checkpoint F
- [x] All 10 dashboard success criteria met
- [ ] Review with the owner → start `SPEC-research.md` (deferred, owner AFK)

Checkpoint F results (2026-11-09): 68 tests pass, ruff clean, dashboard coverage 99% (total 98%). Real browser: 1280px dark mode and 375px light mode look right; no sideways scroll on any of the 4 pages at 375px; Tab reaches every link and button with a visible focus outline. The setup guide now has an "Open the dashboard" section. All 10 dashboard success criteria pass, except that the Ctrl+C half of criterion 1 hasn't been tried by hand (it can't be sent from here; the stop path is covered by the `stop` event test).
