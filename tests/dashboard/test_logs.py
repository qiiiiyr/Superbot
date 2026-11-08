import logging

from fastapi.testclient import TestClient

from superbot.core.config import Settings
from superbot.core.log import setup_logging
from superbot.dashboard.app import create_app


def _client(log_file):
    app = create_app(Settings(anthropic_api_key="sk-test"), log_file=log_file)
    return TestClient(app, base_url="http://127.0.0.1:8000")


def test_shows_last_200_lines_newest_last(engine, tmp_path):
    log_file = tmp_path / "superbot.log"
    log_file.write_text("".join(f"line {i:03d}\n" for i in range(250)), encoding="utf-8")
    page = _client(log_file).get("/logs").text
    assert "line 049" not in page and "line 050" in page
    assert page.index("line 050") < page.index("line 249")


def test_missing_log_file(engine, tmp_path):
    assert "No log yet" in _client(tmp_path / "nope.log").get("/logs").text


def test_api_key_never_shown(engine, tmp_path):
    key = "sk-ant-real-looking-secret"
    setup_logging(log_dir=tmp_path, secrets=[key])
    logging.getLogger("superbot").info("calling Claude with %s", key)
    for h in logging.getLogger().handlers:
        h.flush()
    page = _client(tmp_path / "superbot.log").get("/logs").text
    assert "calling Claude with ***" in page and key not in page
