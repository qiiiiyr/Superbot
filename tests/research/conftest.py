import httpx
import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any real HTTP call from a research test fails loudly."""

    def refuse(self, request):
        raise AssertionError(f"test tried to reach the network: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
