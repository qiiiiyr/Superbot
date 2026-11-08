"""One research run: search words → CJ search → price → Claude score → approvals."""

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import text

from superbot.core import approvals, db, llm
from superbot.core.approvals import executor
from superbot.core.config import Settings
from superbot.research import pricing
from superbot.research.cj import CJClient, CJError

log = logging.getLogger("superbot.research")

MAX_SEARCHES = 5
MAX_DETAILS = 15  # each one also costs a freight call (10 CJ points)
MIN_PRICE_CENTS, MAX_PRICE_CENTS = 300, 4000
AVOID = (
    "branded or trademarked items, supplements, cosmetics, kids' toys, "
    "electronics with batteries, weapons"
)
COLUMNS = (
    "cj_pid vid name image_url keyword cost_cents ship_cents ship_days ship_method"
    " sell_cents profit_cents score reason"
).split()

Ask = Callable[[str], str]


@executor("research.shortlist")
def shortlist(payload: dict) -> dict:
    with db.engine().begin() as c:
        c.execute(
            text("UPDATE products SET status='shortlisted' WHERE id=:i"),
            {"i": payload["product_id"]},
        )
    return {"product_id": payload["product_id"]}


def usd(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def _json_list(reply: str) -> list | None:
    """Claude sometimes wraps JSON in prose or ``` fences; take the outermost [...] block."""
    m = re.search(r"\[.*\]", reply, re.S)
    try:
        data = json.loads(m.group()) if m else None
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _sync_decisions() -> None:
    with db.engine().begin() as c:
        c.execute(
            text(
                "UPDATE products SET status='rejected' WHERE status='proposed' AND action_id IN"
                " (SELECT id FROM actions WHERE status IN ('rejected', 'expired'))"
            )
        )


def shortlisted(limit: int = 100) -> list[dict]:
    """Products the owner approved, newest first."""
    with db.engine().connect() as c:
        rows = c.execute(
            text("SELECT * FROM products WHERE status='shortlisted' ORDER BY id DESC LIMIT :n"),
            {"n": limit},
        )
        return [dict(r._mapping) for r in rows]


def _keywords(settings: Settings, ask: Ask) -> list[str]:
    fixed = [k.strip() for k in settings.research_keywords.split(",") if k.strip()]
    if fixed:
        return fixed[:MAX_SEARCHES]
    with db.engine().connect() as c:
        history = c.execute(
            text(
                "SELECT name, status FROM products WHERE status IN ('shortlisted', 'rejected')"
                " ORDER BY id DESC LIMIT 50"
            )
        ).all()
    feedback = "\n".join(f"- {status}: {name}" for name, status in history) or "- none yet"
    reply = ask(
        "You help a beginner find products to dropship from China to the USA.\n"
        f"Suggest {MAX_SEARCHES} short product search phrases (2-4 words each) for one "
        "beginner-friendly niche: light, unbreakable, no sizes, impulse-buy price $15-$60.\n"
        f"Never suggest: {AVOID}.\n"
        "Products the owner already approved or rejected (learn from this):\n"
        f"{feedback}\n"
        'Reply with only a JSON list of strings, like ["phrase one", "phrase two"].'
    )
    words = _json_list(reply)
    if not words or not all(isinstance(w, str) for w in words):
        log.warning("research: could not read search phrases from Claude's reply")
        return []
    return words[:MAX_SEARCHES]


def _known_pids() -> set[str]:
    with db.engine().connect() as c:
        return set(c.execute(text("SELECT cj_pid FROM products")).scalars())


def _save(p: dict, status: str) -> int:
    row = {k: p.get(k) for k in COLUMNS} | {
        "status": status,
        "found_at": datetime.now(UTC).isoformat(),
    }
    names = ", ".join(row)
    params = ", ".join(":" + k for k in row)
    with db.engine().begin() as c:
        return c.execute(
            text(f"INSERT INTO products ({names}) VALUES ({params}) RETURNING id"), row
        ).scalar_one()


def _score(products: list[dict], ask: Ask) -> list[dict]:
    lines = "\n".join(
        f"{i}. {p['name']} | cost {usd(p['cost_cents'] + p['ship_cents'])} delivered"
        f" | sells for {usd(p['sell_cents'])} | {p['ship_days']} days shipping"
        for i, p in enumerate(products)
    )
    reply = ask(
        "Rate these dropshipping products for a beginner's US store, 1-10, on how likely "
        "they are to sell and how few problems (returns, breakage, complaints) they cause.\n"
        f"Set risky to true for anything that is or may be: {AVOID}.\n"
        f"{lines}\n"
        'Reply with only a JSON list like [{"i": 0, "score": 7, "risky": false, '
        '"reason": "one short sentence"}].'
    )
    rated = _json_list(reply)
    if rated is None:
        log.warning("research: could not read scores from Claude's reply")
        return []
    out = []
    for r in rated:
        try:
            p, score = products[int(r["i"])], int(r["score"])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if r.get("risky") is not False:  # missing or true: leave it out
            continue
        reason = str(r.get("reason", ""))[:300]
        out.append(p | {"score": max(1, min(10, score)), "reason": reason})
    return out


def _propose(p: dict) -> None:
    product_id = _save(p, "proposed")
    action_id = approvals.propose(
        "research.shortlist",
        f"Add to shortlist: {p['name']}",
        {
            "product_id": product_id,
            "image_url": p["image_url"],
            "Product": p["name"],
            "CJ cost": usd(p["cost_cents"]),
            "Shipping": f"{usd(p['ship_cents'])} ({p['ship_method']}, up to {p['ship_days']} days)",
            "Sell price": usd(p["sell_cents"]),
            "Profit per sale": f"{usd(p['profit_cents'])} after card fees",
            "Score": f"{p['score']}/10",
            "Why": p["reason"],
            "Found by searching": p["keyword"],
        },
    )
    with db.engine().begin() as c:
        c.execute(
            text("UPDATE products SET action_id=:a WHERE id=:i"), {"a": action_id, "i": product_id}
        )


def _price(p: dict, cj: CJClient, settings: Settings) -> bool:
    """Fill in cost, shipping and profit. True if the product passes the checks."""
    d = cj.details(p["cj_pid"])
    f = d and cj.freight(d["vid"], settings.max_ship_days)
    if not f:
        return False
    sell = pricing.sell_price(d["cost_cents"], f["ship_cents"], settings.price_multiplier)
    p |= {
        "vid": d["vid"],
        "cost_cents": d["cost_cents"],
        "ship_cents": f["ship_cents"],
        "ship_days": f["days"],
        "ship_method": f["method"],
        "sell_cents": sell,
        "profit_cents": pricing.profit(sell, d["cost_cents"], f["ship_cents"]),
    }
    return pricing.keep(
        p["profit_cents"],
        p["ship_days"],
        min_profit_cents=settings.min_profit_cents,
        max_ship_days=settings.max_ship_days,
    )


def run(cj: CJClient, settings: Settings, ask: Ask = llm.ask) -> int:
    """Returns how many products were proposed."""
    _sync_decisions()
    try:
        keywords = _keywords(settings, ask)
    except llm.LLMError as e:
        log.warning("research: no search phrases (%s)", e)
        return 0

    seen = _known_pids()
    candidates: list[dict] = []
    try:
        for kw in keywords:
            for p in cj.search(kw):
                if p["pid"] not in seen and MIN_PRICE_CENTS <= p["price_cents"] <= MAX_PRICE_CENTS:
                    seen.add(p["pid"])
                    candidates.append(p | {"cj_pid": p["pid"], "keyword": kw})
    except CJError as e:
        log.warning("research: CJ search stopped (%s)", e)

    good: list[dict] = []
    try:
        for p in candidates[:MAX_DETAILS]:
            if _price(p, cj, settings):
                good.append(p)
            else:
                _save(p, "skipped")  # never spend CJ calls on it again
    except CJError as e:
        log.warning("research: CJ details stopped (%s); scoring what was found", e)

    if not good:
        log.info("research: no products passed the price and shipping checks")
        return 0
    try:
        scored = _score(good, ask)
    except llm.LLMError as e:
        log.warning("research: could not score products (%s)", e)
        return 0
    top = sorted(scored, key=lambda p: (-p["score"], -p["profit_cents"]))
    top = top[: settings.research_daily_limit]
    for p in top:
        _propose(p)
    log.info("research: suggested %d product(s) for approval", len(top))
    return len(top)
