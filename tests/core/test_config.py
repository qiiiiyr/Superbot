import pytest

from superbot.core.config import load_settings


def test_missing_key_gives_one_line_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_settings()
    msg = str(exc.value)
    assert msg == "Setting ANTHROPIC_API_KEY is missing — add it to .env"


def test_bad_value_gives_one_line_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("MONTHLY_LLM_CAP_CENTS", "lots")
    with pytest.raises(SystemExit) as exc:
        load_settings()
    assert "\n" not in str(exc.value)
    assert "MONTHLY_LLM_CAP_CENTS" in str(exc.value)


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    s = load_settings()
    assert s.monthly_llm_cap_cents == 500
    assert s.approval_expiry_hours == 48
    assert s.default_model == "claude-haiku-5-5"
    assert s.quality_model == "claude-sonnet-5-5"
    assert s.paused is False
