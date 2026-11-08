# Tasks: research

Plan: [plan-research.md](plan-research.md) · Spec: [SPEC-research.md](../SPEC-research.md)

A task counts as done only when `uv run pytest` passes and `uv run ruff check .` is clean.

---

## Task 1: Pricing math

**Description:** Pure functions in cents. `ship_days("2-5") → 5`, `sell_price(cost, ship, multiplier)` rounded up to the next .99, `fees(sell)` at 2.9% + 30¢ rounded up, `profit(...)`, and `keep(...)` against the minimum profit and maximum shipping days.

**Acceptance criteria:**
- [x] `sell_price(1000, 500, 2.5)` → 3799; an exact .99 stays as it is
- [x] Profit exactly at the minimum is kept; one cent below is dropped; a negative profit is dropped
- [x] `ship_days` handles `"7"`, `"2-5"`, and empty or junk input (returns None, so the product is dropped)

**Verification:** `tests/research/test_pricing.py`, table-driven

**Dependencies:** none · **Files:** `src/superbot/research/__init__.py`, `pricing.py`, test · **Size:** S

---

## Task 2: CJ client

**Description:** `cj.py` with `CJClient(api_key, http=None)` and the methods `search(keyword, size)`, `details(pid)` (returns the first variant) and `freight(vid)` (returns the cheapest option). Token is cached in `settings_kv`, there is a 1.1s gap between calls, and `CJError` is raised on HTTP 429, a non-200 status, or `result: false`.

**Acceptance criteria:**
- [x] The second client reuses the stored token (token endpoint called once in total); an expired token is refreshed
- [x] HTTP 429 → `CJError`, with no retry
- [x] Calls are spaced at least 1.1s apart (checked with a fake clock, not real sleeps)
- [x] Fields are parsed from the docs' example shapes; a product with missing fields returns None

**Verification:** `tests/research/test_cj.py` with `httpx.MockTransport`; a guard fails any test that opens a real socket

**Dependencies:** none · **Files:** `pyproject.toml` (httpx to main), `cj.py`, test · **Size:** M

---

## Checkpoint G
- [x] Tests and ruff clean; no network in tests

---

## Task 3: Products table, the run, and the executor

**Description:**
- Migration `0002_products`.
- `finder.run(client, settings)` does: sync rejected rows → keywords → search → dedupe and price filter → details and freight → pricing → score → propose the top N.
- Executor `research.shortlist` marks the product row `shortlisted`.

**Acceptance criteria:**
- [x] One run with a fake CJ and a fake LLM proposes at most `RESEARCH_DAILY_LIMIT` approvals with the full payload
- [x] A product already in the table is never searched for details again or proposed again
- [x] Approving and running marks it `shortlisted`; a rejected or expired approval → `rejected` on the next run
- [x] A product Claude flags as a trademark risk, bad LLM JSON, or a `CJError` partway through → no crash; whatever was found before the error is still proposed
- [x] Call caps are respected (5 searches, 15 details, 15 freight)

**Verification:** `tests/research/test_finder.py`; migration up and down test

**Dependencies:** Tasks 1, 2 · **Files:** `migrations/versions/0002_products.py`, `finder.py`, `research/__init__.py`, test · **Size:** M

---

## Task 4: Daily job and settings

**Description:**
- Add the new `Settings` fields.
- `scheduler.add_job(..., hour=)` uses a cron trigger in local time.
- `research.register(settings)` adds the job only when the key is set.
- `main` calls it and masks `CJ_API_KEY`.
- `JOB_NAMES` gets "Find products".

**Acceptance criteria:**
- [x] No key → log line "research skipped: no CJ_API_KEY", no job, and the bot runs normally
- [x] With a key, the job `research.find` is scheduled at `RESEARCH_HOUR`
- [x] The CJ key never shows up in the log file (test)
- [x] `.env.example` lists the new settings with no real values

**Verification:** `tests/research/test_job.py`; `test_main` still passes

**Dependencies:** Task 3 · **Files:** `config.py`, `scheduler.py`, `research/__init__.py`, `main.py`, `dashboard/app.py` (JOB_NAMES), `.env.example` · **Size:** M

---

## Checkpoint H
- [x] The end-to-end flow with fakes works (see plan); tests and ruff clean

---

## Task 5: Dashboard

**Description:**
- The approval card shows the product image for `research.shortlist` items.
- A new `/products` page lists shortlisted products (image, name, cost, sell price, profit, shipping days), newest first.
- The nav gets a "Products" link.

**Acceptance criteria:**
- [x] The image shows only for `https://` URLs, with alt text; a `<script>` in a product name is escaped
- [x] `/products` has an empty state ("No products yet") and fits at 375px with no sideways scroll

**Verification:** `tests/dashboard/test_products.py`; one browser check with fake data

**Dependencies:** Task 3 · **Files:** `dashboard/app.py`, `templates/base.html`, `approvals.html`, `products.html`, `style.css` · **Size:** M

---

## Task 6: Setup guide and real run

**Description:** A `docs/setup.md` section in beginner words: make a free CJ account, find the API key, paste it into `.env`, restart, and where suggestions appear.

**Acceptance criteria:**
- [x] Guide section written
- [ ] **Owner-only:** one real run with your key produces suggestions; check that the shipping days look right

**Dependencies:** Tasks 4, 5 · **Files:** `docs/setup.md` · **Size:** S

---

## Checkpoint I
- [ ] All spec success criteria met; coverage ≥ 90%; owner review

---

## Results (2026-11-09, owner AFK)

- **Checkpoint G:** 99 tests pass, ruff clean. The no-network guard is in `tests/research/conftest.py`.
- **Checkpoint H:** 118 tests pass. With a fake CJ and a fake LLM:
  - a run proposes the products;
  - approving one shortlists it, and rejecting one stops it coming back;
  - with no key, research is skipped with one log line.
- **Checkpoint I:** 127 tests pass. Total coverage is 97% (cj 93%, finder 93%, pricing 100%).
  - Browser check at 375px on fake data: the Approvals and Products pages have no sideways scroll, and the images loaded.
  - The owner's real-key run and review are deferred until a CJ key exists.
- **Changes from the spec:**
  - Shipping uses the cheapest option *within* `MAX_SHIP_DAYS`, not the cheapest overall. The cheapest overall is often a 40-day option, which the shipping check would then drop.
  - Products that fail the price or shipping checks are saved as `skipped`, so no CJ calls are spent on them again. Good products outside the daily limit stay unsaved and can come back.
  - The Status page says when research is off (no key).
- **Bug caught by a test:** when the client had to fetch a token first, its next call skipped the 1.1s gap. Fixed.
- **Not checked:**
  - Real CJ responses (the fakes are copied from CJ's docs).
  - The free-account points quota.
  - Whether `logisticAging` is in days.
