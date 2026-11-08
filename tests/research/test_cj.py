import pytest
from sqlalchemy import text

from superbot.research.cj import CJClient, CJError

from .fake_cj import FakeCJ, product

KEY = "CJ123@api@secret"


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.now += s


def client(fake: FakeCJ, clock: Clock | None = None) -> CJClient:
    clock = clock or Clock()
    return CJClient(KEY, http=fake.http(), clock=clock.time, sleep=clock.sleep)


def test_token_is_stored_and_reused(engine):
    fake = FakeCJ()
    client(fake).search("dog bowl")
    client(fake).search("cat toy")
    assert fake.calls.count("authentication/getAccessToken") == 1


def test_expired_token_is_fetched_again(engine):
    fake = FakeCJ()
    client(fake).search("x")
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE settings_kv SET value='2000-01-01T00:00:00+00:00'"
                " WHERE key='cj_token_expires'"
            )
        )
    client(fake).search("x")
    assert fake.calls.count("authentication/getAccessToken") == 2


def test_search_parses_products(engine):
    fake = FakeCJ(
        [product("P1", "Dog Bowl", "4.50"), product("P2", "Lamp", "2.59 -- 4.99"), {"id": "P3"}]
    )
    found = client(fake).search("x")
    assert found == [
        {
            "pid": "P1",
            "name": "Dog Bowl",
            "image_url": "https://cf.cjdropshipping.com/P1.jpg",
            "price_cents": 450,
        },
        {
            "pid": "P2",
            "name": "Lamp",
            "image_url": "https://cf.cjdropshipping.com/P2.jpg",
            "price_cents": 259,
        },
    ]  # P3 has no name or price, so it is skipped


def test_details_and_cheapest_freight_within_options(engine):
    c = client(FakeCJ())
    assert c.details("P1") == {"vid": "V-P1", "cost_cents": 450}
    # "Slow" is cheaper but takes 40 days, so the cheapest within 15 days wins
    assert c.freight("V-P1", max_days=15) == {"method": "USPS+", "ship_cents": 320, "days": 12}
    assert c.freight("V-P1", max_days=2) is None


def test_429_raises_and_never_retries(engine):
    fake = FakeCJ()
    fake.status_for["product/listV2"] = 429
    with pytest.raises(CJError, match="429"):
        client(fake).search("x")
    assert fake.calls.count("product/listV2") == 1


def test_calls_are_spaced_out(engine):
    clock = Clock()
    c = client(FakeCJ(), clock)
    c.search("a")  # token + search
    c.search("b")
    assert len(clock.slept) == 2 and all(s >= 1.1 - 1e-9 for s in clock.slept)
