# Spec: core

Module id: `core` (see [CAPABILITY-MAP.md](CAPABILITY-MAP.md)) · Depends on: none · Status: **APPROVED** (2026-11-09)

## Objective

`core` is the foundation every other module plugs into. It has no business features of its own. It provides:

1. **Settings and secrets:** read from `.env`, checked at startup, never printed in logs.
2. **Database:** one SQLite file, with tables created and upgraded automatically on start.
3. **Approval queue:** the safety gate. A module never spends money, places an order or publishes anything directly. It *proposes* an action, you approve or reject it, and only then does `core` run it, **exactly once**.
4. **Claude API client:** one shared client with a **monthly spending cap**. It records every call's cost and refuses new calls once the cap is reached.
5. **Scheduler:** runs module jobs on a timer (e.g. "check new orders every 10 min").
6. **Pause switch:** one setting that stops all jobs and all approved actions immediately.
7. **Logging:** a rotating log file plus an audit trail of every approval decision.

**User story:** As the store owner, I start the bot with one command. It refuses to do anything risky without my approval, never runs the same approved order twice, never overspends my AI budget, and I can pause everything at once.

## Tech Stack

| Piece | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Beginner-friendly; good Shopify, HTTP and Anthropic libraries |
| Package / env manager | `uv` | One installer that also installs Python; one command to set up |
| Settings | `pydantic-settings` 2.x | Reads `.env` and checks types, with clear errors |
| Database | SQLite via SQLAlchemy 2.x + Alembic | Single file now; same code works with Postgres in the cloud later |
| Scheduler | APScheduler 3.x | Runs in the same process; no extra service to install |
| AI | `anthropic` (official SDK); default model `claude-haiku-5-5`, `claude-sonnet-5-5` for quality tasks | Cheap by default, configurable per task |
| Tests / lint | pytest, ruff | Standard |

The web dashboard (FastAPI) belongs to the `dashboard` module, not here.

## Commands

Run once, in PowerShell, to set up:
```
winget install --id=astral-sh.uv -e
uv sync
copy .env.example .env      # then fill in your keys
```

Daily use:
```
Run:    uv run superbot
Test:   uv run pytest
Lint:   uv run ruff check . --fix
Format: uv run ruff format .
```

## Project Structure

```
dropship-superbot/
  CAPABILITY-MAP.md        → module index (approved)
  SPEC-core.md             → this file; one SPEC-<module>.md per module
  pyproject.toml           → dependencies and the `superbot` command
  .env.example             → every setting, with no real values (safe to share)
  .env                     → your real keys (never shared or committed)
  src/superbot/
    main.py                → entry point: load settings, migrate DB, start scheduler
    core/
      config.py            → Settings class
      db.py                → engine, session, base model
      approvals.py         → approval queue + executor registry
      llm.py               → Claude client with spend cap
      scheduler.py         → job registration, honours pause switch
      log.py               → logging setup, secret masking
    migrations/            → Alembic database upgrades
  tests/core/              → tests for each file above
  data/                    → superbot.db and logs/ (not committed)
  docs/                    → beginner setup guide
  tasks/                   → plan.md, todo.md
```

## Code Style

Modules register *what to do once approved*. They never run the action themselves:

```python
# src/superbot/fulfillment/actions.py (how a later module will use core)
from superbot.core.approvals import executor, propose

@executor("fulfillment.place_order")
def place_order(payload: dict) -> dict:
    """Runs only after the owner approves; core guarantees at most once."""
    order = cj_client.create_order(payload["shopify_order_id"], payload["items"])
    return {"cj_order_id": order.id}

propose(
    kind="fulfillment.place_order",
    title="Order #1042: 2× LED desk lamp from CJ ($18.40)",
    payload={"shopify_order_id": 1042, "items": [...]},
)
```

Conventions: `snake_case` functions and files, type hints on every public function, action kinds named `<module>.<verb>_<noun>`, money stored as **integer cents** (never floats), times stored in UTC. Comments explain *why*, not what.

## Approval queue rules

```
pending ──approve──→ approved ──run──→ executed
   │                      └──error──→ failed
   ├──reject──→ rejected
   └──timeout─→ expired
```

- An approved action runs **at most once**. Approving twice, double-clicking, or restarting mid-run never runs it twice; the status change is a single atomic database update.
- Failed actions are **not retried automatically**. You see the error and decide. This prevents duplicate supplier orders.
- Pending actions **expire after 48 hours** (configurable), since supplier prices and stock change. Executors must re-check price and stock before acting, and fail if either changed beyond a limit.
- Every decision is written to the audit trail: what, when, approved or rejected, and the result.
- While **paused**, approvals can still be recorded but nothing executes, and scheduled jobs skip their runs.

## Testing Strategy

- **pytest**, tests in `tests/core/`, each test using its own temporary SQLite database.
- Tests **never call the real Claude API** or any external service; they use a fake client.
- Every transition in the approval diagram above has a test, including two approvals happening at the same moment (it must run once).
- Spend cap: the boundary just under, at, and over the cap.
- Coverage target for `core`: **90%**, since everything else depends on it.

## Boundaries

- **Always:** run `uv run pytest` and `ruff` before calling a task done; keep money in cents; route every external side effect (money, publishing, messages) through the approval queue; mask secrets in logs.
- **Ask first:** adding a dependency not listed above; changing the database schema of an existing table; changing the default spend cap or expiry time.
- **Never:** put real keys in any file except `.env`; let any code path spend, order or publish without an approved queue item; retry a failed money action automatically; delete failing tests to get to green.

## Success Criteria

1. On a clean Windows PC, the setup commands above followed by `uv run superbot` start the bot and log `ready` within 10 seconds.
2. A missing or invalid required setting stops startup with a one-line message naming the setting, not a stack trace.
3. A proposed action shows up as `pending` and survives a restart.
4. Approving runs its executor exactly once, including under two simultaneous approvals and a restart during the run.
5. A rejected or expired action never runs.
6. An executor error leaves the action `failed` with the error text stored, and it is not retried.
7. With pause on, no scheduled job runs and no approved action executes. Turning pause off resumes both.
8. Every Claude call records tokens and cost. When this month's cost reaches the cap, the next call fails with `BudgetExceeded` without contacting the API.
9. No log line contains an API key (a test logs the settings object and checks that the keys are masked).
10. `uv run pytest` passes with core coverage ≥ 90%, and `ruff check` is clean.

## Decisions (resolved 2026-11-09)

1. Monthly Claude API cap: **$5**.
2. Approval expiry: **48 hours**.
3. `uv` is the one thing you install.
4. The project folder is a git repository.

Still open from the map, but **not needed until later modules**: CJ-only fulfillment (needed for `fulfillment`), email-only support (needed for `support`), and the pricing rule (needed for `listings`).
