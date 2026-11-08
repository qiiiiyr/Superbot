import pytest

from superbot.research import pricing


@pytest.mark.parametrize(
    ("cost", "ship", "mult", "sell"),
    [
        (1000, 500, 2.5, 3799),  # 3750 → next .99
        (1000, 0, 2.5, 2599),  # 2500 → 2599
        (1520, 0, 2.5, 3899),  # 3800 → 3899, never rounds down
        (1000, 396, 2.5, 3499),  # 3490 → 3499
        (1000, 400, 1, 1499),  # 1400 → 1499
        (1, 0, 1.1, 99),
    ],
)
def test_sell_price_rounds_up_to_99(cost, ship, mult, sell):
    assert pricing.sell_price(cost, ship, mult) == sell


def test_exact_99_stays():
    assert pricing.sell_price(3799, 0, 1) == 3799


def test_fees_round_up():
    assert pricing.fees(3799) == 111 + 30  # 110.17 → 111
    assert pricing.fees(1000) == 29 + 30


@pytest.mark.parametrize(
    ("text", "days"),
    [("7", 7), ("2-5", 5), ("12-50", 50), (" 3 - 8 ", 8), ("", None), ("soon", None), (None, None)],
)
def test_ship_days(text, days):
    assert pricing.ship_days(text) == days


def test_profit():
    # 3799 − 1000 − 500 − 141
    assert pricing.profit(3799, 1000, 500) == 2158


@pytest.mark.parametrize(
    ("profit", "days", "kept"),
    [
        (1000, 10, True),  # exactly at the minimum
        (999, 10, False),
        (-50, 3, False),
        (5000, 15, True),
        (5000, 16, False),
        (5000, None, False),
    ],
)
def test_keep(profit, days, kept):
    assert pricing.keep(profit, days, min_profit_cents=1000, max_ship_days=15) is kept
