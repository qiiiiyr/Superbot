# Spec: dashboard

Module id: `dashboard` (see [CAPABILITY-MAP.md](CAPABILITY-MAP.md)) · Depends on: `core` · Status: **APPROVED** (2026-11-09, with defaults)

## Objective

A web page on your PC where you run the bot day to day, with no terminal needed after start-up:

1. **Approvals:** see every pending action in plain words (what, how much, when it expires) and approve or reject it with one click.
2. **History:** see what ran, what failed and why. Anything marked "interrupted — check manually" stands out.
3. **Status:** running or paused, with a Pause/Resume button; this month's AI spend against the cap; when each background job last ran.
4. **Logs:** the last 200 lines of `data/logs/superbot.log` (keys are already masked by `core`).

**User story:** As the store owner, I run `uv run superbot`, open `http://127.0.0.1:8000`, and handle everything the bot is waiting on from that page. A website I happen to visit can't approve anything behind my back.

Out of scope for now: editing settings or keys in the browser (you edit `.env`), password login (needed before the cloud move; tracked in the map), module-specific pages (each later module adds its own if it needs one), and live updates (you refresh the page).

## Tech Stack

| Piece | Choice | Why |
|---|---|---|
| Web framework | FastAPI | Approved in the capability map; small and well documented |
| Server | uvicorn | The standard way to run FastAPI; runs inside the bot's process |
| Templates | Jinja2, autoescape on | Server-rendered HTML, no frontend build step; autoescape stops AI- or supplier-written text from injecting HTML |
| Forms | python-multipart | FastAPI needs it to read HTML form posts |
| Tests | FastAPI `TestClient` (needs httpx, dev only) | Tests the pages without a browser or open port |

**New dependencies (approving this spec approves them):** `fastapi`, `uvicorn`, `jinja2`, `python-multipart`, and `httpx` as a dev dependency. Versions are pinned in `uv.lock` when installed and checked against each project's docs at that point (source-driven-development).

No JavaScript framework and no CSS framework. One small hand-written stylesheet.

## Commands

No new commands. `uv run superbot` now also serves the dashboard and logs `ready — open http://127.0.0.1:8000`. `superbot pause` and `superbot resume` keep working without the dashboard.

## Project Structure

```
src/superbot/dashboard/
  app.py            → FastAPI app: routes, the Host/Origin/CSRF checks
  templates/        → base.html, approvals.html, history.html, status.html, logs.html
  static/style.css
tests/dashboard/
  test_pages.py     → each page renders and shows the right items
  test_actions.py   → approve, reject, pause and resume through the form posts
  test_security.py  → foreign Host/Origin rejected, missing or wrong CSRF token rejected, HTML escaped
```

`core` gains two small read functions the pages need: `approvals.list_recent(limit)` and a last-run time per scheduler job. Neither changes the database schema.

## Code Style

Routes stay thin: they call `core` and render a template. No business rules in the dashboard.

```python
@app.post("/actions/{action_id}/approve")
def approve(action_id: int, csrf: str = Form(...)):
    check_csrf(csrf)
    try:
        approvals.approve(action_id)
    except ApprovalError as e:  # already decided or expired: tell the owner, don't crash
        return redirect("/", flash=str(e))
    return redirect("/", flash="Approved. It runs within 30 seconds unless paused.")
```

Every change uses POST followed by a redirect, so refreshing the page never repeats a click. Every page works with the keyboard alone and uses real `<button>` and `<label>` elements.

## Security

The bot binds to `127.0.0.1` only. That stops other computers, but not a malicious website in your own browser, so:

- **Host check:** requests whose `Host` isn't `127.0.0.1:<port>` or `localhost:<port>` get a 400. This blocks DNS-rebinding attacks.
- **Origin check:** a POST whose `Origin` (or `Referer` when `Origin` is missing) isn't the dashboard's own address gets a 403.
- **CSRF token:** each form carries a random token generated at start-up and compared in constant time. A missing or wrong token gets a 403.
- **Escaping:** Jinja autoescape stays on. Never use `|safe` on anything that came from AI, suppliers, Shopify or customers.
- **No secrets on any page.** The status page shows that a key is set, never the key itself.

## Testing Strategy

pytest with `TestClient` against the temporary-database fixture from `core`. No real server, network or browser in tests. Each success criterion below has a test. Coverage for `dashboard` is at least 90%. One manual check in a real browser per checkpoint.

## Boundaries

- **Always:** go through `core` for every change (approve, reject, pause); POST and redirect for changes; escape everything; keep the Host, Origin and CSRF checks on every POST.
- **Ask first:** adding JavaScript beyond a few lines; adding any page that changes settings or keys; binding to anything other than `127.0.0.1`.
- **Never:** run an executor from a web request (only the scheduler runs actions); show secrets; turn off autoescape; add a dashboard route that spends money or publishes without going through the approval queue.

## Success Criteria

1. `uv run superbot` serves the dashboard at `http://127.0.0.1:8000` and logs the address; Ctrl+C stops both the bot and the dashboard.
2. The approvals page lists every pending action with its title, a readable view of its details, and how long until it expires.
3. Approve and Reject change the status through `core` and show a confirmation message. Clicking twice, or on an action that is already decided, shows a clear message and changes nothing.
4. The history page shows the last 50 decided or finished actions, with the result or error. "Interrupted — check manually" items are highlighted.
5. The status page shows running or paused (and whether `PAUSED=true` in `.env` forces it), a working Pause/Resume button, this month's AI spend against the cap in dollars, and each job's last run time.
6. The logs page shows the last 200 log lines with no API key in them.
7. A POST with a foreign `Origin` or `Host`, or a missing or wrong CSRF token, is refused and changes nothing.
8. Text like `<script>` in an action's title or details shows up as text, not as HTML.
9. Every page is usable with the keyboard alone and readable at 1280px and 375px wide.
10. `uv run pytest` passes with dashboard coverage at least 90%, and `ruff check` is clean.

## Decisions (resolved 2026-11-09)

1. Port **8000**, changeable with a `DASHBOARD_PORT` setting.
2. Settings stay **read-only** in the dashboard; you edit `.env`.
3. **No auto-refresh**; refresh the page yourself.
