from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from superbot.core import llm
from superbot.core.config import Settings
from superbot.core.llm import BudgetExceeded


class FakeClient:
    def __init__(self, input_tokens=1000, output_tokens=500, stop="end_turn"):
        self.calls: list[dict] = []
        self.usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        self.stop = stop
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text="hi")],
            usage=self.usage,
            stop_reason=self.stop,
        )


@pytest.fixture
def fake(engine):
    client = FakeClient()
    llm.configure(Settings(anthropic_api_key="sk-test", monthly_llm_cap_cents=100), client)
    return client


def _spend(engine, cents):
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO llm_usage (at, model, input_tokens, output_tokens, cost_cents)"
                " VALUES (:t, 'x', 0, 0, :c)"
            ),
            {"t": datetime.now(UTC).isoformat(), "c": cents},
        )


def _usage(engine):
    with engine.connect() as c:
        return c.execute(
            text("SELECT model, input_tokens, output_tokens, cost_cents FROM llm_usage")
        ).all()


def test_records_usage_and_rounds_cost_up(engine, fake):
    assert llm.ask("hello") == "hi"
    # haiku: 1000*10 + 500*50 = 35_000 / 1M cents → 0.035 → rounds up to 1
    assert _usage(engine) == [("claude-haiku-5-5", 1000, 500, 1)]
    assert fake.calls[0]["model"] == "claude-haiku-5-5"


def test_quality_uses_sonnet(engine, fake):
    llm.ask("hello", quality=True)
    assert fake.calls[0]["model"] == "claude-sonnet-5-5"


def test_cost_math():
    assert llm.cost_cents("claude-sonnet-5-5", 1_000_000, 1_000_000) == 1200
    assert llm.cost_cents("claude-haiku-5-5", 0, 0) == 0
    assert llm.cost_cents("claude-haiku-5-5", 200_000, 0) == 10  # long-prompt rate: 200k*50/1M
    with pytest.raises(ValueError, match="No price"):
        llm.cost_cents("claude-mystery", 1, 1)


def test_just_under_cap_goes_through(engine, fake):
    _spend(engine, 99)
    llm.ask("hi")
    assert len(fake.calls) == 1


@pytest.mark.parametrize("spent", [100, 150])
def test_at_or_over_cap_raises_before_calling(engine, fake, spent):
    _spend(engine, spent)
    with pytest.raises(BudgetExceeded):
        llm.ask("hi")
    assert fake.calls == []


def test_last_month_spend_does_not_count(engine, fake):
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO llm_usage (at, model, input_tokens, output_tokens, cost_cents)"
                " VALUES ('2000-01-01T00:00:00+00:00', 'x', 0, 0, 999)"
            )
        )
    llm.ask("hi")
    assert len(fake.calls) == 1


def test_refusal_is_recorded_then_raised(engine):
    client = FakeClient(stop="refusal")
    llm.configure(Settings(anthropic_api_key="sk-test"), client)
    with pytest.raises(llm.LLMError, match="refused"):
        llm.ask("hi")
    assert len(_usage(engine)) == 1
