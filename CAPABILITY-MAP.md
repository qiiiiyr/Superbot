# Capability Map: Dropship Superbot

Status: **APPROVED** (2026-11-09)

## What you told me (interview)

| Topic | Answer |
|---|---|
| Independence | Standalone app; calls the Claude API for AI tasks; does not need Claude Code to run |
| Automate | Product research, store listings, order fulfillment, customer support, ads |
| Platform | Shopify store + AliExpress / CJ Dropshipping suppliers |
| Autonomy | Bot prepares; **you approve** every spend, order and publish |
| Interface | Web dashboard |
| Hosting | Your Windows PC first, cloud VPS later |
| Experience | Beginner: run and configure, don't write code |
| Accounts | None yet |
| Market | USA / worldwide English, USD |
| Budget | Start small, scale up |
| LLM | Claude API |
| Niche | Bot finds one |

## Assumptions (correct any of these now)

1. **Language: Python 3.12.** It's the most beginner-friendly option and has good Shopify/HTTP libraries.
2. **Dashboard: FastAPI plus plain server-rendered HTML.** You run one command and open `http://localhost:8000`. No separate frontend build step.
3. **Database: SQLite**, a single file with no server to install. It can move to Postgres when we go to the cloud.
4. **Testing: a free Shopify Partner development store.** Nothing gets paid or goes live until you choose to.
5. **Suppliers: CJ Dropshipping first.** It has an official API. AliExpress order automation needs approval as an AliExpress affiliate or dropshipping API partner, so it starts as research only (prices and products).
6. **Ads start as "draft + recommend".** The Meta and TikTok ad APIs need business verification and app review. The bot writes ad copy and budgets, and you launch the ads until access is approved.
7. **Secrets** (API keys) go in a local `.env` file that is never shared or committed.
8. **Login:** the dashboard listens on `localhost` only while it's on your PC. It gets a password login before it moves to the cloud.

## Modules

| Module id | Responsibility | Depends on |
|---|---|---|
| `core` | Config and secrets, database, scheduler, **approval queue**, Claude API client, logging | none |
| `dashboard` | Web UI: approve/reject queue, status, logs, settings | core |
| `research` | Find trending products, check supplier cost vs. sell price, score margin | core |
| `listings` | Create and update Shopify products (AI title/description, pricing rules, images) | core, research |
| `fulfillment` | New Shopify order → place CJ order (after approval) → sync tracking back | core, listings |
| `support` | Read customer emails, draft replies using order and tracking data, queue for approval | core, fulfillment |
| `ads` | Draft ad copy, audiences and budgets for the products that sell; track ad spend you enter | core, listings |

Build order: `core` → `dashboard` → `research` → `listings` → `fulfillment` → `support`, `ads`

Each module ships and is testable on its own. After `listings` you already have a working "find a product → approve → it's on my store" loop.

## Skills I'll use, and when

| Phase | Skills |
|---|---|
| Now (spec) | spec-driven-development, interview-me |
| Each module's spec | api-and-interface-design (module contracts), source-driven-development (Shopify, CJ, Claude API docs), claude-api |
| Plan | planning-and-task-breakdown |
| Build | incremental-implementation, test-driven-development, security-and-hardening (keys, payments, customer data), frontend-ui-engineering (dashboard) |
| Before calling a module done | code-review-and-quality, observability-and-instrumentation |
| Docs | documentation-and-adrs (setup guide written for a beginner) |
| Move to cloud | shipping-and-launch, ci-cd-and-automation |

Skipped as not relevant: academic research, graphify, figcraft, game-development, slides/docx/xlsx.

## Things that cost money (you'll need these later, not now)

- Shopify plan once you go live (the dev store is free while building)
- Claude API: roughly a few dollars a month at small volume, with a cap set in the config
- CJ Dropshipping: free account; you pay per order
- Domain, ads, and later a VPS (about $5–10/month)

## Open questions

1. Is it OK to start fulfillment with **CJ only**, and add AliExpress ordering later if you get API access?
2. Customer support channel: **email only** at first (Shopify's contact form sends to email)?
3. Should prices follow a simple rule such as `sell = (supplier cost + shipping) × 2.5`, editable in the dashboard?
