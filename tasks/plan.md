# Implementation Plan: core

Module: `core` · Spec: [SPEC-core.md](../SPEC-core.md) · Status: **APPROVED** (2026-11-09)
Task list: [todo.md](todo.md)

## Overview

Build the foundation the other modules plug into. That means settings, logging, the database, the approval queue (the safety gate), the pause switch, the capped Claude client and the scheduler, all started by `uv run superbot`. There are no business features yet. When this is done, a later module can register an `@executor`, call `propose(...)`, and rely on core to run that action only after approval, and only once.

## Dependency graph

```
skeleton (pyproject, entry point)
   └── config + log
         └── db + migrations
               ├── approvals: propose / approve / reject / expire / audit
               │     └── execution: atomic claim, run once, record failure
               │           └── pause switch (blocks execution)
               ├── llm: usage table + spend cap
               └── scheduler (honours pause; runs executor loop + expiry sweep)
                     └── main wiring + setup guide
```

Each task builds on the one before it, so the work is sequential. `llm` (Task 7) only needs `db` and could be built in parallel with Tasks 4–6. It is small, so splitting it off isn't worth the coordination.

## Architecture decisions

1. **New `executing` state (needs your OK).** The spec's diagram goes `approved → executed/failed`. To guarantee "at most once" across restarts, the runner first claims an item with one atomic update: `UPDATE … SET status='executing' WHERE id=? AND status='approved'`. It goes ahead only if exactly one row changed.
   - If the bot crashes mid-run, the item stays `executing`. On the next start, core marks it `failed` with the message "interrupted — check manually". It is never re-run, because the supplier order may already have gone through.
   - This adds one state to the diagram. You never act on it; it just shows "running".
2. **Pause switch stored in the database (needs your OK).** It goes in a small `settings_kv` table, not in `.env`, so it takes effect on the next scheduler tick without a restart.
   - It is controlled by `uv run superbot pause` and `uv run superbot resume`, and later by a dashboard button.
   - A `PAUSED=true` line in `.env` also forces pause at startup, as a safety override.
3. **Approve/reject are plain functions for now.** These are `approve(id)`, `reject(id, reason)` and `list_pending()`. The dashboard module adds the buttons, and core has no web code.
   - Until then, approvals can only be made from tests or a Python shell. That's fine because no module proposes anything yet.
4. **Model prices live in config, not code.** A price table (dollars per million input/output tokens per model) sits in `config.py` with defaults that override from `.env`. The prices are checked against Anthropic's current pricing page while Task 7 is built. I won't guess them.
5. **SQLite in WAL mode, Alembic in batch mode.** WAL lets the scheduler thread and a future dashboard read while the executor writes. Batch mode is required for Alembic to alter SQLite tables. Postgres later needs no code change.
6. **APScheduler pinned to 3.x.** Version 4 has a different API, and pinning prevents a surprise break.
7. **Executors run in the scheduler's executor loop.** They don't run inside `approve()`. Approving only records the decision, and a job runs approved items every 30 seconds (configurable). That keeps approval instant and puts every side effect in one place, where the pause switch can stop it.

## Task list

### Phase 1: Foundation
- [ ] Task 1: Project skeleton, `uv run superbot` logs `ready`
- [ ] Task 2: Settings with one-line errors, plus logging with secret masking
- [ ] Task 3: Database, migrations run on start

### Checkpoint A (after Tasks 1–3)
- [ ] `uv run pytest` and `uv run ruff check .` are clean
- [ ] `uv run superbot` creates `data/superbot.db`, logs `ready`, and exits cleanly on Ctrl+C
- [ ] Review with you before the approval queue

### Phase 2: Safety gate
- [ ] Task 4: Propose, approve, reject and expire, with an audit trail
- [ ] Task 5: Run approved actions exactly once, with failure recorded and no retry
- [ ] Task 6: Pause switch (DB flag + CLI) blocks execution

### Checkpoint B (after Tasks 4–6)
- [ ] Every transition in the approval diagram has a passing test, including two approvals at once and a restart mid-run
- [ ] Review with you, since this is the highest-risk part

### Phase 3: Services and wiring
- [ ] Task 7: Claude client with usage recording and the $5 monthly cap
- [ ] Task 8: Scheduler honours pause; built-in executor loop and expiry sweep
- [ ] Task 9: Wire everything in `main`, plus a beginner setup guide

### Checkpoint C (complete)
- [ ] All 10 success criteria in SPEC-core.md are met
- [ ] Core coverage ≥ 90%, ruff is clean
- [ ] Review with you; then the `dashboard` spec starts

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Two runs of the same approved order (duplicate supplier charge) | High | Atomic conditional update with a rowcount check; a stuck `executing` item becomes `failed`, never re-run; concurrency test with 2 threads |
| SQLite "database is locked" under concurrent writes | Med | WAL mode, a 5s busy timeout, short transactions |
| Claude model prices change | Med | Price table in config; recorded cost errs high if unsure; cap checked before every call |
| `uv` install issues on Windows | Med | Task 9 guide covers the PowerShell execution-policy prompt and a `uv --version` check |
| Alembic can't alter SQLite tables | Low | `render_as_batch=True` from the first migration |
| APScheduler 4 breaking change | Low | Pin `apscheduler>=3.10,<4` |
| Secrets leaking into logs or tracebacks | High | `SecretStr` for every key, a logging filter that masks known key patterns, and a test that logs the settings object |

## Open questions

None blocking. The two decisions marked "needs your OK" above are the only design choices beyond the spec.
