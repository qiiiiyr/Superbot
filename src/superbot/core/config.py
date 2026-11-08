from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: SecretStr
    monthly_llm_cap_cents: int = 500
    approval_expiry_hours: int = 48
    default_model: str = "claude-haiku-5-5"
    quality_model: str = "claude-sonnet-5-5"
    paused: bool = False
    dashboard_port: int = 8000


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        err = e.errors()[0]
        name = str(err["loc"][0]).upper()
        if err["type"] == "missing":
            raise SystemExit(f"Setting {name} is missing — add it to .env") from None
        raise SystemExit(f"Setting {name} is invalid: {err['msg']}") from None


# Cents per million tokens: (input, output). Source: Anthropic pricing, checked 2026-11-09
# via the claude-api skill (table cached 2026-10-06). Re-check before changing models.
PRICES_CENTS_PER_MTOK: dict[str, tuple[int, int]] = {
    "claude-haiku-5-5": (10, 50),
    "claude-sonnet-5-5": (200, 1000),
}
# Haiku 5.5 charges more once a prompt goes past 100K input tokens.
LONG_PROMPT_PRICES: dict[str, tuple[int, tuple[int, int]]] = {
    "claude-haiku-5-5": (100_000, (50, 250)),
}
