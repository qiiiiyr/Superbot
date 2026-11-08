"""Money math for one product, in integer cents. No I/O."""

import math
import re
from decimal import Decimal

FEE_RATE = Decimal("0.029")  # Shopify Payments, basic plan
FEE_FIXED_CENTS = 30


def sell_price(cost_cents: int, ship_cents: int, multiplier: float) -> int:
    """(cost + shipping) × multiplier, rounded up to the next price ending in .99."""
    raw = math.ceil((cost_cents + ship_cents) * Decimal(str(multiplier)))
    return max(99, math.ceil((raw - 99) / 100) * 100 + 99)


def fees(sell_cents: int) -> int:
    return math.ceil(sell_cents * FEE_RATE) + FEE_FIXED_CENTS


def profit(sell_cents: int, cost_cents: int, ship_cents: int) -> int:
    return sell_cents - cost_cents - ship_cents - fees(sell_cents)


def ship_days(aging: str | None) -> int | None:
    """CJ gives shipping time as "2-5"; use the slow end. Unit assumed to be days."""
    numbers = re.findall(r"\d+", aging or "")
    return max(map(int, numbers)) if numbers else None


def keep(profit_cents: int, days: int | None, *, min_profit_cents: int, max_ship_days: int) -> bool:
    return days is not None and days <= max_ship_days and profit_cents >= min_profit_cents
