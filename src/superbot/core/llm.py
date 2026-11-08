"""The only way modules talk to Claude: tracks every call's cost and enforces the monthly cap."""

from datetime import UTC, datetime

import anthropic
from sqlalchemy import text

from superbot.core import db
from superbot.core.config import LONG_PROMPT_PRICES, PRICES_CENTS_PER_MTOK, Settings


class LLMError(Exception):
    pass


class BudgetExceeded(LLMError):
    pass


_settings: Settings | None = None
_client = None


def configure(settings: Settings, client=None) -> None:
    global _settings, _client
    _settings = settings
    _client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())


def cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    if model not in PRICES_CENTS_PER_MTOK:
        raise ValueError(f"No price for model {model!r} — add it to PRICES_CENTS_PER_MTOK")
    price_in, price_out = PRICES_CENTS_PER_MTOK[model]
    threshold, long_prices = LONG_PROMPT_PRICES.get(model, (None, None))
    if threshold is not None and input_tokens > threshold:
        price_in, price_out = long_prices
    return -(-(input_tokens * price_in + output_tokens * price_out) // 1_000_000)  # ceil, ints only


def month_spend_cents() -> int:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    with db.engine().connect() as c:
        return c.execute(
            text("SELECT COALESCE(SUM(cost_cents), 0) FROM llm_usage WHERE at >= :s"), {"s": start}
        ).scalar_one()


def ask(prompt: str, *, quality: bool = False, max_tokens: int = 16000) -> str:
    if _settings is None:
        raise LLMError("llm.configure() was not called")
    model = _settings.quality_model if quality else _settings.default_model
    cost_cents(model, 0, 0)  # fail on an unpriced model before spending anything
    # shortcut: two concurrent calls can both pass this check; lock if jobs run in parallel
    spent = month_spend_cents()
    if spent >= _settings.monthly_llm_cap_cents:
        raise BudgetExceeded(
            f"Monthly AI budget used: {spent}¢ of {_settings.monthly_llm_cap_cents}¢"
        )
    response = _client.messages.create(
        model=model, max_tokens=max_tokens, messages=[{"role": "user", "content": prompt}]
    )
    u = response.usage
    with db.engine().begin() as c:
        c.execute(
            text(
                "INSERT INTO llm_usage (at, model, input_tokens, output_tokens, cost_cents)"
                " VALUES (:t, :m, :i, :o, :c)"
            ),
            {
                "t": datetime.now(UTC).isoformat(),
                "m": model,
                "i": u.input_tokens,
                "o": u.output_tokens,
                "c": cost_cents(model, u.input_tokens, u.output_tokens),
            },
        )
    if response.stop_reason == "refusal":
        raise LLMError("Claude refused this request")
    return "".join(b.text for b in response.content if b.type == "text")
