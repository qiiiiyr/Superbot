import logging

from superbot.core.config import load_settings
from superbot.core.log import setup_logging


def test_secrets_are_masked(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-very-secret")
    s = load_settings()
    setup_logging(tmp_path / "logs", [s.anthropic_api_key.get_secret_value()])
    log = logging.getLogger("superbot")
    log.info("settings %s", s)
    log.info("raw key %s", s.anthropic_api_key.get_secret_value())
    for h in logging.getLogger().handlers:
        h.flush()
    text = (tmp_path / "logs" / "superbot.log").read_text(encoding="utf-8")
    assert "sk-very-secret" not in text
    assert "***" in text


def test_secret_in_traceback_is_masked(tmp_path):
    setup_logging(tmp_path, ["sk-in-traceback"])
    try:
        raise RuntimeError("auth failed for sk-in-traceback")
    except RuntimeError:
        logging.getLogger("superbot").exception("job failed")
    for h in logging.getLogger().handlers:
        h.flush()
    text = (tmp_path / "superbot.log").read_text(encoding="utf-8")
    assert "job failed" in text and "RuntimeError" in text
    assert "sk-in-traceback" not in text
