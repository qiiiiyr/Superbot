import json

import pytest
from sqlalchemy import inspect, text

from superbot.core import approvals, db, llm
from superbot.core.config import Settings
from superbot.research import finder
from superbot.research.cj import CJClient

from .fake_cj import FakeCJ, product


def settings(**kw) -> Settings:
    return Settings(anthropic_api_key="sk-test", **kw)


class FakeLLM:
    """Answers the two research prompts; scores are set per product name."""

    def __init__(self, keywords=("dog bowl",), scores=None, risky=()):
        self.keywords = list(keywords)
        self.scores = scores or {}
        self.risky = set(risky)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if prompt.startswith("You help"):
            return "Here you go:\n```json\n" + json.dumps(self.keywords) + "\n```"
        rows = []
        for line in prompt.splitlines():
            if line[:1].isdigit() and ". " in line:
                i, rest = line.split(". ", 1)
                name = rest.split(" | ")[0]
                rows.append(
                    {
                        "i": int(i),
                        "score": self.scores.get(name, 5),
                        "risky": name in self.risky,
                        "reason": f"why {name}",
                    }
                )
        return json.dumps(rows)


def cj(fake: FakeCJ) -> CJClient:
    return CJClient("CJ123@api@secret", http=fake.http(), sleep=lambda s: None)


def statuses() -> dict[str, str]:
    with db.engine().connect() as c:
        return dict(c.execute(text("SELECT cj_pid, status FROM products")).all())


def test_migration_adds_products(engine, db_url):
    assert "products" in inspect(engine).get_table_names()


def test_run_proposes_best_with_full_payload(engine):
    fake = FakeCJ([product("P1", "Dog Bowl"), product("P2", "Cat Brush"), product("P3", "Mat")])
    ai = FakeLLM(scores={"Dog Bowl": 6, "Cat Brush": 9, "Mat": 2})
    assert finder.run(cj(fake), settings(research_daily_limit=2), ai) == 2

    pending = approvals.list_pending()
    assert [a["title"] for a in pending] == [
        "Add to shortlist: Cat Brush",
        "Add to shortlist: Dog Bowl",
    ]
    p = pending[0]["payload"]
    assert p == {
        "product_id": p["product_id"],
        "image_url": "https://cf.cjdropshipping.com/P2.jpg",
        "Product": "Cat Brush",
        "CJ cost": "$4.50",
        "Shipping": "$3.20 (USPS+, up to 12 days)",
        "Sell price": "$19.99",  # (4.50 + 3.20) × 2.5 = 19.25 → 19.99
        "Profit per sale": "$11.41 after card fees",  # 19.99 − 4.50 − 3.20 − 0.88
        "Score": "9/10",
        "Why": "why Cat Brush",
        "Found by searching": "dog bowl",
    }
    # the third was good but outside today's limit, so it stays unsaved and can come back
    assert statuses() == {"P1": "proposed", "P2": "proposed"}


def test_approve_shortlists_and_reject_never_comes_back(engine):
    fake = FakeCJ([product("P1", "Dog Bowl"), product("P2", "Cat Brush")])
    finder.run(cj(fake), settings(), FakeLLM())
    keep, drop = approvals.list_pending()
    approvals.approve(keep["id"])
    approvals.reject(drop["id"])
    approvals.run_approved()

    fake.calls.clear()
    assert finder.run(cj(fake), settings(), FakeLLM()) == 0
    assert statuses() == {"P1": "shortlisted", "P2": "rejected"}
    assert "product/query" not in fake.calls  # known products are never looked up again


def test_filters_price_shipping_profit_and_risk(engine):
    fake = FakeCJ(
        [
            product("CHEAP", "Sticker", "1.00"),  # under $3, never looked up
            product("PRICEY", "Chair", "99.00"),  # over $40
            product("OK", "Dog Bowl"),
            product("RISK", "Nike Socks"),
        ]
    )
    ai = FakeLLM(risky={"Nike Socks"})
    assert finder.run(cj(fake), settings(), ai) == 1
    assert statuses() == {"OK": "proposed"}  # the risky one is left unsaved for a later look
    assert fake.calls.count("product/query") == 2


def test_low_profit_is_saved_as_skipped(engine):
    fake = FakeCJ([product("P1", "Dog Bowl")])
    assert finder.run(cj(fake), settings(min_profit_cents=5000), FakeLLM()) == 0
    assert statuses() == {"P1": "skipped"}


def test_no_shipping_within_limit_is_skipped(engine):
    fake = FakeCJ([product("P1", "Dog Bowl")])
    assert finder.run(cj(fake), settings(max_ship_days=2), FakeLLM()) == 0
    assert statuses() == {"P1": "skipped"}


def test_fixed_keywords_skip_claude_and_are_capped(engine):
    fake = FakeCJ([])
    ai = FakeLLM()
    finder.run(cj(fake), settings(research_keywords="a, b,c,d,e,f,g"), ai)
    assert fake.calls.count("product/listV2") == finder.MAX_SEARCHES
    assert not any(p.startswith("You help") for p in ai.prompts)


def test_details_are_capped(engine):
    fake = FakeCJ([product(f"P{i}", f"Thing {i}") for i in range(20)])
    finder.run(cj(fake), settings(), FakeLLM())
    assert fake.calls.count("product/query") == finder.MAX_DETAILS
    assert fake.calls.count("logistic/freightCalculate") == finder.MAX_DETAILS


def test_cj_error_midway_still_proposes_what_was_found(engine):
    fake = FakeCJ([product("P1", "Dog Bowl"), product("P2", "Cat Brush")])

    real = fake.handler

    def fail_second_freight(request):
        path = request.url.path
        if path.endswith("freightCalculate") and fake.calls.count("logistic/freightCalculate"):
            fake.calls.append("logistic/freightCalculate")
            import httpx

            return httpx.Response(429, json={"result": False})
        return real(request)

    fake.handler = fail_second_freight
    assert finder.run(cj(fake), settings(), FakeLLM()) == 1


@pytest.mark.parametrize("reply", ["no idea", "[not json", '{"a": 1}', "[1, 2]"])
def test_bad_claude_keywords_mean_no_search(engine, reply):
    fake = FakeCJ()
    assert finder.run(cj(fake), settings(), lambda prompt: reply) == 0
    assert "product/listV2" not in fake.calls


def test_bad_scores_propose_nothing(engine):
    fake = FakeCJ()

    def ai(prompt):
        return '["dog bowl"]' if prompt.startswith("You help") else "I'd rate them all highly!"

    assert finder.run(cj(fake), settings(), ai) == 0
    assert approvals.list_pending() == []


def test_budget_used_up_stops_quietly(engine):
    def broke(prompt):
        raise llm.BudgetExceeded("Monthly AI budget used")

    assert finder.run(cj(FakeCJ()), settings(), broke) == 0


def test_claude_hears_about_past_decisions(engine):
    fake = FakeCJ([product("P1", "Dog Bowl")])
    finder.run(cj(fake), settings(), FakeLLM())
    approvals.reject(approvals.list_pending()[0]["id"])
    ai = FakeLLM()
    finder.run(cj(FakeCJ([])), settings(), ai)
    assert "- rejected: Dog Bowl" in ai.prompts[0]
