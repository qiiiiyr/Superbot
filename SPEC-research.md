# Spec: research module

Status: **APPROVED** (2026-11-09, with defaults)

## Objective

Once a day, the bot looks for products on CJ Dropshipping, works out what each one would really cost to sell in the USA, and suggests the profitable ones to the owner. Each suggestion shows up on the Approvals page. **Approve** puts the product on a shortlist, which the `listings` module will later publish to Shopify. **Reject** means it won't be suggested again.

This module spends no money and publishes nothing. The only costs are Claude API calls, which already have a monthly cap, and free CJ API calls.

Done when:

- A daily job finds up to `RESEARCH_DAILY_LIMIT` new products and each one becomes a `research.shortlist` approval.
- Each approval shows the product name, image, CJ cost, shipping cost and days, the suggested sell price, profit per sale, and why the bot picked it.
- Approving marks the product `shortlisted`, and the dashboard's new **Products** page lists it.
- The same CJ product is never suggested twice.
- With no `CJ_API_KEY` set, the job logs one line ("research skipped: no CJ_API_KEY") and the rest of the bot keeps running.

## How it works (one run)

1. **Pick search words.** Claude (`default_model`, Haiku) suggests 5 search phrases for a beginner-friendly niche, using the last 50 approved and rejected products as feedback. The owner can set fixed phrases instead with `RESEARCH_KEYWORDS`.
2. **Search CJ.** Call `GET /product/listV2` with `keyWord`, `countryCode=US` and `orderBy=1` (most listed by other stores, used as the popularity signal), plus `size=20`.
3. **Filter cheaply first.** Drop products already in the database and products whose CJ price is outside `$3–$40`.
4. **Get the variant and shipping.** For the best remaining candidates, call `GET /product/query?pid=` to get the first variant `vid`, then `POST /logistic/freightCalculate` (CN → US, qty 1). Keep the cheapest shipping option.
5. **Do the money math** (integer cents):
   - `sell = round_up_to_.99((cost + shipping) × PRICE_MULTIPLIER)`
   - `fees = sell × 2.9% + 30¢` (Shopify Payments, basic plan)
   - `profit = sell − cost − shipping − fees`
   - Keep the product only if `profit ≥ MIN_PROFIT_CENTS` and shipping time ≤ `MAX_SHIP_DAYS`.
6. **Score and explain.** Claude rates each survivor 1–10 and writes one sentence on why it might sell or what the risk is (fragile, sized clothing, branded or trademarked, and so on). Anything flagged as a likely trademark is dropped.
7. **Propose.** The top `RESEARCH_DAILY_LIMIT` products by score, then profit, become approvals.

## CJ API facts this relies on

Source: developers.cjdropshipping.com, API 2.0, read 2026-11-09.

- **Base URL:** `https://developers.cjdropshipping.com/api2.0/v1/`
- **Auth:** `POST authentication/getAccessToken` with `{"apiKey": ...}`. It returns an `accessToken` that lasts 180 days and is sent in the `CJ-Access-Token` header. The bot stores the token in `settings_kv` and refreshes it with `refreshAccessToken` when it expires, so it doesn't fetch a new token every run.
- **Limits:**
  - Free accounts: 1 request per second. The client waits 1.1s between calls.
  - There is also a daily points quota, and a freight calculation costs 10 points. The bot caps calls per run (search ≤ 5, details and freight ≤ 15 each).
  - On HTTP 429 the run stops and logs the error. It doesn't retry in a loop.
- **Shipping time:** freight returns `logisticAging` as a string such as `"2-5"`. The bot uses the higher number as days. The unit isn't stated in the docs, so this is assumed to be days.

## Tech stack

Same as core. HTTP calls use **httpx**, which is already installed because the Anthropic SDK needs it, and is moved from dev-only to a main dependency. No new packages.

## Data

Migration `0002_products` adds one table:

```
products(id, cj_pid UNIQUE, vid, name, image_url, keyword,
         cost_cents, ship_cents, ship_days, ship_method,
         sell_cents, profit_cents, score, reason,
         status,          -- proposed | shortlisted | rejected
         action_id,       -- the approval it belongs to
         found_at)
```

The executor marks a product `shortlisted` when its approval runs. A reject or expiry marks it `rejected` the next time the job runs.

## Settings (new, all optional in `.env`)

| Name | Default | Meaning |
|---|---|---|
| `CJ_API_KEY` | (empty) | From your CJ account. Research is skipped without it |
| `RESEARCH_KEYWORDS` | (empty) | Comma-separated search phrases. Empty means Claude picks them |
| `RESEARCH_DAILY_LIMIT` | 5 | Most suggestions per day |
| `PRICE_MULTIPLIER` | 2.5 | Sell price = (cost + shipping) × this |
| `MIN_PROFIT_CENTS` | 1000 | Skip products earning under $10 per sale |
| `MAX_SHIP_DAYS` | 15 | Skip slower shipping |
| `RESEARCH_HOUR` | 9 | Hour of day (local time) the job runs |

## Project structure

```
src/superbot/research/
  cj.py        → small CJ client: token, list, details, freight (1 req/s)
  pricing.py   → money math only, pure functions
  finder.py    → the run: keywords → search → filter → price → score → propose
  __init__.py  → registers the research.shortlist executor and the daily job
src/superbot/dashboard/templates/products.html  → shortlist page
alembic/versions/0002_products.py
tests/research/  → test_pricing, test_cj (fake HTTP), test_finder, test_products_page
```

## Testing strategy

- **pricing.py:** table tests for rounding to .99, fees, and the edge cases (zero shipping, profit exactly at the minimum, a cost that makes profit negative).
- **cj.py:** `httpx.MockTransport` with responses copied from the docs' examples. Covers token reuse and refresh, a 429 stopping the run, and a missing key. **Tests never call the real CJ API.**
- **finder.py:** a fake CJ client and a fake LLM. Covers dedupe, filters, trademark drop, the limit, and the approval payload shape.
- **Dashboard:** the Products page renders, escapes names, and fits at 375px.
- Coverage stays ≥ 90%.
- **Manual check (needs your CJ key):** run the job once and see real suggestions appear.

## Boundaries

- **Always:**
  - Wait between CJ calls, cap calls per run, and store money as cents.
  - Put every suggestion through the approval queue.
  - Mask `CJ_API_KEY` and the access token in logs.
- **Ask first:** new dependencies, other data sources (Google Trends, TikTok, AliExpress), raising the call caps.
- **Never:**
  - Buy, order or publish anything from this module.
  - Scrape websites.
  - Retry in a loop after a rate-limit error.

## Assumptions (correct any of these)

1. The **popularity signal is CJ's "listed by most stores" sort, plus Claude's judgement.** There is no trend data. Google Trends has no official API, and the unofficial libraries break often.
2. Pricing follows the capability map's suggested rule, **sell = (cost + shipping) × 2.5**, which you can change in `.env`.
3. **USA only, first variant only.** Products with many sizes or colours still get suggested, priced on their first variant. `listings` handles all the variants later.
4. **Fees assume the Shopify basic plan with Shopify Payments** (2.9% + 30¢). Ad costs aren't counted yet; `ads` will add them.

## What you need to do (only when we reach the manual check)

1. Make a **free CJ Dropshipping account**.
2. Copy its **API key** into `.env` as `CJ_API_KEY=...`.

Nothing is paid. I'll build and test everything with fake data before then.

## Open questions

1. Is "CJ popularity + Claude judgement" enough for now, or do you want a real trend source? A real one may need a paid tool or account.
2. Are 5 suggestions per day, at least $10 profit, and at most 15 days shipping the right starting numbers?
3. Any product types to always avoid? Suggested defaults: no supplements, cosmetics, kids' toys, electronics with batteries, or weapons, because these carry legal and returns risk.
