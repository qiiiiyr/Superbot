# Implementation Plan: research

Spec: [SPEC-research.md](../SPEC-research.md) · Tasks: [todo-research.md](todo-research.md) · Done before this: [plan.md](plan.md) (core), [plan-dashboard.md](plan-dashboard.md)

## Overview

The order is: the money math first, because it's pure and carries the most risk. Then the CJ client, tested only against fake HTTP. Then the run that turns search results into approvals. Then the daily job and the dashboard pages. Tests never call the real CJ API. The one real run waits for the owner's CJ key, at the end.

## Architecture Decisions

- **Product rows live in `research`, not `core`.**
  - Migration `0002_products` sits in the existing `src/superbot/migrations/versions/` folder, so `db.migrate()` picks it up with no change.
  - The product store is a few functions in `finder.py`. No new layer.
- **Approval payload carries everything the card shows**, including name, image URL, cost, shipping, sell price, profit, score and reason. The executor `research.shortlist` only needs the payload's `product_id` to mark the row `shortlisted`.
- **Rejected and expired approvals are synced at the start of each run.** The product rows that belong to them become `rejected`. This avoids adding hooks to `core.approvals`.
- **CJ token is cached in `settings_kv`** under the keys `cj_token` and `cj_token_expires`. The client fetches a new token only when there is none or it has less than a day left. On a 401 it fetches once more, then stops.
- **Rate limit: one sleep in one place.** `cj.py` waits until 1.1s has passed since the last call. On HTTP 429 or any CJ error code it raises `CJError`, which ends the run.
- **Daily job time.**
  - `scheduler.add_job` gets an optional `hour=` argument that uses APScheduler's `cron` trigger in the PC's local time zone. Interval jobs stay as they are.
  - The job is registered only when `CJ_API_KEY` is set. Otherwise start-up logs "research skipped: no CJ_API_KEY".
- **Claude calls.**
  - Two prompts go through the existing `llm.ask()`: keyword ideas and scoring. Each asks for JSON only.
  - On bad JSON the run logs it and skips that step. With no keywords, nothing is searched; with no score, the product isn't proposed. It never guesses.
  - Both prompts tell Claude to drop branded or trademarked products and the "always avoid" list from the spec defaults.
- **Secrets.** `main` passes `CJ_API_KEY` to the logging mask too. The access token is only ever sent in a header and is never logged.
- **httpx** moves from the dev group to main dependencies with `uv add httpx`. It is already installed through `anthropic`, so it adds no new package.
- **Images:**
  - The approval card and the Products page show `<img src>` only when the URL starts with `https://`, with `alt` set to the product name and `loading="lazy"`.
  - Autoescape stays on.

## Task List

### Phase 1: Numbers and supplier
- [x] Task 1: Pricing math (`pricing.py`) with table tests
- [x] Task 2: CJ client: token, search, details, freight, rate limit (fake HTTP)

### Checkpoint G
- [x] Tests and ruff clean; pricing edge cases covered; no test touches the network

### Phase 2: From search to approval
- [x] Task 3: Products table, the run, and the `research.shortlist` executor
- [x] Task 4: Daily job, settings, and key masking wired into `main`

### Checkpoint H
- [x] With a fake CJ and a fake LLM, one run creates approvals. Approving one shortlists the product, rejecting one stops it coming back, and a missing key skips research cleanly

### Phase 3: See it
- [x] Task 5: Approval card image and a Products page in the dashboard
- [x] Task 6: Setup guide CJ section; owner's real-key run

### Checkpoint I
- [ ] All spec success criteria met. The real-key run is owner-only and stays deferred until the key exists

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Rounding or fee mistake shows a fake profit | High: you'd list products that lose money | Task 1 first, pure functions, table tests including negative profit |
| CJ response shape differs from the docs | Medium | Fakes copied from the docs' examples; missing fields skip that product with a log line, never crash the run; the real-key run in Task 6 confirms |
| Burning CJ's daily points quota | Medium | Hard caps per run (5 searches, 15 details, 15 freight), one run per day |
| Claude suggests a trademarked or banned item | Medium | Prompt rule plus owner approval on every product |
| Token leaks in logs | Medium | Never logged; key masked; a test greps the log |
| `logisticAging` isn't in days | Low | Take the higher number; check on the real run |

## Open Questions

None. The spec was approved with defaults.
