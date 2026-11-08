"""Small CJ Dropshipping API 2.0 client: token, product search, details, freight.

Docs: https://developers.cjdropshipping.com/ (read 2026-11-09). Free accounts get 1 request/second.
"""

import logging
import math
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import text

from superbot.core import db
from superbot.research import pricing

BASE = "https://developers.cjdropshipping.com/api2.0/v1/"
GAP_SECONDS = 1.1
log = logging.getLogger("superbot.research.cj")


class CJError(Exception):
    """CJ refused or failed; the run stops instead of retrying."""


def cents(value) -> int | None:
    """'4.50' → 450; '2.59 -- 4.99' → 259 (lowest); junk → None."""
    m = re.search(r"\d+(?:\.\d+)?", str(value) if value is not None else "")
    return math.ceil(Decimal(m.group()) * 100) if m else None


def _kv_get(key: str) -> str | None:
    with db.engine().connect() as c:
        return c.execute(text("SELECT value FROM settings_kv WHERE key=:k"), {"k": key}).scalar()


def _kv_set(key: str, value: str) -> None:
    with db.engine().begin() as c:
        c.execute(
            text(
                "INSERT INTO settings_kv (key, value) VALUES (:k, :v)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            ),
            {"k": key, "v": value},
        )


class CJClient:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._key = api_key
        self._http = http or httpx.Client(timeout=30)
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None

    def _call(self, method: str, path: str, *, auth: bool = True, **kwargs):
        # token first: fetching it is a call too, so the wait must come after it
        headers = {"CJ-Access-Token": self._token()} if auth else {}
        if self._last is not None:
            wait = self._last + GAP_SECONDS - self._clock()
            if wait > 0:
                self._sleep(wait)
        try:
            r = self._http.request(method, BASE + path, headers=headers, **kwargs)
        except httpx.HTTPError as e:
            raise CJError(f"{path}: {type(e).__name__}") from None
        finally:
            self._last = self._clock()
        if r.status_code != 200:
            raise CJError(f"{path}: HTTP {r.status_code}")
        body = r.json()
        if not body.get("result"):
            raise CJError(f"{path}: {body.get('code')} {body.get('message')}")
        return body.get("data")

    def _token(self) -> str:
        token, expires = _kv_get("cj_token"), _kv_get("cj_token_expires")
        if (
            token
            and expires
            and datetime.fromisoformat(expires) > datetime.now(UTC) + timedelta(days=1)
        ):
            return token
        # shortcut: fetch a fresh token instead of using refreshToken; CJ returns the same
        # token for 24h and it lasts 180 days, so this runs about twice a year
        data = self._call(
            "POST", "authentication/getAccessToken", auth=False, json={"apiKey": self._key}
        )
        try:
            expiry = datetime.fromisoformat(data["accessTokenExpiryDate"])
        except (KeyError, TypeError, ValueError):
            expiry = datetime.now(UTC) + timedelta(days=170)
        _kv_set("cj_token", data["accessToken"])
        _kv_set("cj_token_expires", expiry.isoformat())
        log.info("CJ access token renewed")
        return data["accessToken"]

    def search(self, keyword: str, size: int = 20) -> list[dict]:
        data = self._call(
            "GET",
            "product/listV2",
            params={"keyWord": keyword, "countryCode": "US", "orderBy": 1, "page": 1, "size": size},
        )
        found = []
        for group in (data or {}).get("content") or []:
            for p in group.get("productList") or []:
                price = cents(p.get("sellPrice"))
                if p.get("id") and p.get("nameEn") and price:
                    found.append(
                        {
                            "pid": p["id"],
                            "name": p["nameEn"],
                            "image_url": p.get("bigImage") or "",
                            "price_cents": price,
                        }
                    )
        return found

    def details(self, pid: str) -> dict | None:
        """First variant only; listings handles the rest."""
        variants = (self._call("GET", "product/query", params={"pid": pid}) or {}).get("variants")
        if not variants:
            return None
        v = variants[0]
        cost = cents(v.get("variantSellPrice"))
        return {"vid": v["vid"], "cost_cents": cost} if v.get("vid") and cost else None

    def freight(self, vid: str, max_days: int) -> dict | None:
        """Cheapest CN → US option that arrives within max_days."""
        options = self._call(
            "POST",
            "logistic/freightCalculate",
            json={
                "startCountryCode": "CN",
                "endCountryCode": "US",
                "products": [{"quantity": 1, "vid": vid}],
            },
        )
        best = None
        for o in options or []:
            price, days = cents(o.get("logisticPrice")), pricing.ship_days(o.get("logisticAging"))
            if price is not None and days is not None and days <= max_days:
                if best is None or price < best["ship_cents"]:
                    best = {"method": o.get("logisticName", ""), "ship_cents": price, "days": days}
        return best
