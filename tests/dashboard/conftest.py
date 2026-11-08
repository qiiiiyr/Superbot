import pytest
from fastapi.testclient import TestClient

from superbot.core.config import Settings
from superbot.dashboard.app import create_app


@pytest.fixture
def client(engine):
    return TestClient(
        create_app(Settings(anthropic_api_key="sk-test")), base_url="http://127.0.0.1:8000"
    )


ORIGIN = {"Origin": "http://127.0.0.1:8000"}


@pytest.fixture
def post(client):
    """POST like the real page does: same Origin, correct CSRF token."""

    def _post(url, data=None, headers=ORIGIN):
        form = {"csrf": client.app.state.csrf, **(data or {})}
        return client.post(url, data=form, headers=headers, follow_redirects=False)

    return _post
