# Tasks: core

Plan: [plan.md](plan.md) · Spec: [SPEC-core.md](../SPEC-core.md)

Every task counts as done only when `uv run pytest` passes and `uv run ruff check .` is clean (spec Boundaries: Always).

---

## Task 1: Project skeleton

**Description:** Create the installable project so `uv sync` and `uv run superbot` work. `main` is a stub that logs `ready` and waits for Ctrl+C.

**Acceptance criteria:**
- [x] `pyproject.toml` declares Python 3.12, the spec's dependencies (APScheduler pinned `<4`), and a `superbot` script pointing to `superbot.main:run`
- [x] `.gitignore` excludes `.env`, `data/`, `.venv/` and caches; `.env.example` lists every setting with no real values
- [x] pytest (with coverage) and ruff are configured in `pyproject.toml`

**Verification:**
- [x] `uv sync` succeeds; `uv run superbot` prints `ready`
- [x] A smoke test imports `superbot.main`

**Dependencies:** None

**Files:** `pyproject.toml`, `.gitignore`, `.env.example`, `src/superbot/__init__.py`, `src/superbot/main.py`, `tests/test_smoke.py`

**Size:** S

---

## Task 2: Settings and logging

**Description:** A `Settings` class reads `.env`, and `log.py` sets up console logging plus a rotating file under `data/logs/`, with secrets masked.

**Acceptance criteria:**
- [x] A missing or invalid required setting exits with one line naming it (e.g. `Setting ANTHROPIC_API_KEY is missing — add it to .env`), with no traceback
- [x] Defaults: `MONTHLY_LLM_CAP_CENTS=500`, `APPROVAL_EXPIRY_HOURS=48`, `DEFAULT_MODEL=claude-haiku-5-5`, `QUALITY_MODEL=claude-sonnet-5-5`
- [x] Keys are `SecretStr`; logging the settings object or a string containing a key shows `***`

**Verification:**
- [x] Tests: bad value → one-line error; masking test (success criterion 9)

**Dependencies:** Task 1

**Files:** `src/superbot/core/config.py`, `src/superbot/core/log.py`, `tests/core/test_config.py`, `tests/core/test_log.py`

**Size:** S

---

## Task 3: Database and migrations

**Description:** SQLAlchemy engine and session for `data/superbot.db` (WAL, busy timeout), with an Alembic baseline that runs automatically on start. The baseline tables are `actions`, `audit_log`, `llm_usage` and `settings_kv`.

**Acceptance criteria:**
- [x] On start, a fresh install creates the DB at the latest migration; an existing DB is upgraded
- [x] Alembic uses batch mode; times are stored in UTC; money columns are integer cents
- [x] Tests get their own temporary database through a pytest fixture

**Verification:**
- [x] Test: migrate an empty temporary DB and check that all 4 tables exist
- [x] Manual: `uv run superbot` creates `data/superbot.db`

**Dependencies:** Task 2

**Files:** `src/superbot/core/db.py`, `src/superbot/migrations/` (env + first revision), `alembic.ini`, `tests/conftest.py`, `tests/core/test_db.py`

**Size:** M

### Checkpoint A
- [x] pytest and ruff are clean
- [x] `uv run superbot` → DB created, `ready` logged
- [ ] Review with the owner (deferred, owner AFK)

Checkpoint A results (2026-11-09): 7 tests pass, ruff clean; a fresh start creates `data/superbot.db` at revision 0001 and logs `ready`; file log verified. Note: the venv lives at `C:\Users\riqi2\sb-venv` (set `UV_PROJECT_ENVIRONMENT`) because the long folder path breaks SQLAlchemy's compiled module.

---

## Task 4: Approval queue (propose → decide)

**Description:** `propose()`, `approve()`, `reject()`, `list_pending()` and an expiry function. Each decision writes an audit row.

**Acceptance criteria:**
- [x] `propose(kind, title, payload)` stores a `pending` item, which is still there after a restart (success criterion 3); an unknown `kind` (no registered executor) is refused
- [x] Only `pending` items can be approved or rejected; anything else raises a clear error
- [x] `expire_old()` moves pending items older than 48h to `expired`; every transition writes an audit row (who, what, when)

**Verification:**
- [x] Tests: each transition plus the illegal ones; the restart test reopens the DB

**Dependencies:** Task 3

**Files:** `src/superbot/core/approvals.py`, `tests/core/test_approvals.py`

**Size:** M

---

## Task 5: Exactly-once execution

**Description:** The `@executor(kind)` registry and `run_approved()`, which claims each approved item atomically, runs it, and records the result or the error.

**Acceptance criteria:**
- [x] Claim is `UPDATE … SET status='executing' WHERE id=? AND status='approved'`; the executor runs only if rowcount == 1
- [x] Success → `executed` with the result stored; an exception → `failed` with the error text, and it is not retried (success criterion 6)
- [x] On startup, a leftover `executing` item → `failed` ("interrupted — check manually"); rejected or expired items never run (success criterion 5)

**Verification:**
- [x] Tests: 2 threads call `run_approved()` on the same item and the executor runs once (success criterion 4); a simulated crash leaves the item `executing` and the restart marks it failed

**Dependencies:** Task 4

**Files:** `src/superbot/core/approvals.py`, `tests/core/test_execution.py`

**Size:** M

---

## Task 6: Pause switch

**Description:** A pause flag in `settings_kv`, with `superbot pause` and `superbot resume` CLI commands. `run_approved()` does nothing while paused.

**Acceptance criteria:**
- [x] `is_paused()` reads the DB flag; `PAUSED=true` in `.env` forces pause
- [x] While paused, approve/reject still work but nothing executes; after resume, approved items run
- [x] `uv run superbot pause` and `resume` print the new state and exit

**Verification:**
- [x] Tests: pause → approve → run → nothing ran; resume → run → it ran

**Dependencies:** Task 5

**Files:** `src/superbot/core/approvals.py` (or a small `pause.py` if that reads more clearly), `src/superbot/main.py`, `tests/core/test_pause.py`

**Size:** S

### Checkpoint B
- [x] Every approval-diagram transition is tested, including concurrency and restart
- [ ] Review with the owner (highest-risk part) (deferred, owner AFK)

Checkpoint B results (2026-11-09): 21 tests pass, ruff clean. Covered: propose/approve/reject/expire, illegal decisions, unknown kind refused, restart keeps pending items, 2 threads → executor runs once, error → failed and never retried, crash mid-run → `executing` → marked failed on restart, pause blocks execution and resume runs it. `uv run superbot pause` / `resume` work without an API key. The pause code lives in `core/pause.py`.

---

## Task 7: Claude client with spend cap

**Description:** `llm.ask(prompt, *, quality=False)` wraps the `anthropic` SDK. It records tokens and cost per call and refuses calls over the monthly cap.

**Acceptance criteria:**
- [x] Each call stores model, input/output tokens and cost in cents (rounded up) in `llm_usage` (success criterion 8)
- [x] When this UTC month's total is ≥ the cap, `BudgetExceeded` is raised before any API call
- [x] The prices table lives in config; check the values against Anthropic's pricing page during this task (claude-api skill), not from memory

**Verification:**
- [x] Tests with a fake client: just under the cap → call goes through; at the cap → raises; over the cap → raises; the fake records zero API calls once the cap is hit
- [x] No test touches the network

**Dependencies:** Task 3

**Files:** `src/superbot/core/llm.py`, `src/superbot/core/config.py` (prices), `tests/core/test_llm.py`

**Size:** M

---

## Task 8: Scheduler

**Description:** An APScheduler 3 wrapper. `add_job(fn, minutes=)` skips the run while paused. It registers two built-in jobs: the executor loop (every 30s) and the expiry sweep (hourly).

**Acceptance criteria:**
- [x] A registered job doesn't run while paused and runs again after resume (success criterion 7)
- [x] A job that raises is logged and doesn't stop the scheduler
- [x] The built-in jobs call `run_approved()` and `expire_old()`

**Verification:**
- [x] Tests call the job wrapper directly (no real waiting): paused → skipped; error → logged, scheduler still running

**Dependencies:** Tasks 6, 7

**Files:** `src/superbot/core/scheduler.py`, `tests/core/test_scheduler.py`

**Size:** S

---

## Task 9: Wiring and setup guide

**Description:** `main.run()` loads settings, sets up logging, migrates, recovers stuck items, starts the scheduler, logs `ready`, and shuts down cleanly. It comes with a beginner guide.

**Acceptance criteria:**
- [x] `uv run superbot` logs `ready` within 10s on a fresh clone (success criterion 1); Ctrl+C stops it cleanly
- [x] Core coverage ≥ 90%, ruff is clean (success criterion 10)
- [x] `docs/setup.md` covers installing uv, `uv sync`, filling `.env`, running, pausing, and where the logs are, in plain words

**Verification:**
- [x] Test: `run()` with a temporary DB reaches `ready` (scheduler started, then stopped)
- [ ] Manual: follow `docs/setup.md` in a fresh PowerShell window

**Dependencies:** Task 8

**Files:** `src/superbot/main.py`, `docs/setup.md`, `tests/test_main.py`

**Size:** S

### Checkpoint C
- [x] All 10 spec success criteria are met
- [ ] Review with the owner → start `SPEC-dashboard.md` (deferred, owner AFK)

Checkpoint C results (2026-11-09): 33 tests pass, coverage 98% (main.py 91%: only the Ctrl+C branch is untested), ruff clean. `uv run superbot` logged `ready` in 5.4s on this PC with a placeholder key. Criteria 1–10 all pass. Two caveats: criterion 1 was checked on this PC, not a clean one; and spec Decision 4 (the folder is a git repo) is not done yet, since nothing gets committed until the owner asks. Prices: Haiku 5.5 $0.10/$0.50 per MTok ($0.50/$2.50 above 100K-token prompts), Sonnet 5.5 $2/$10, from the claude-api skill's table cached 2026-10-06. Still open: following `docs/setup.md` in a fresh PowerShell window, and a run with a real key (one real API call).
