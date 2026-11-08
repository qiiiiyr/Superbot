import pytest

from superbot.core import pause


def test_foreign_host_is_refused(client):
    r = client.get("/status", headers={"Host": "evil.example"})
    assert r.status_code == 400


def test_localhost_name_is_allowed(client):
    assert client.get("/status", headers={"Host": "localhost:8000"}).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Referer": "http://evil.example/page"},
        {},  # no Origin and no Referer
    ],
)
def test_foreign_or_missing_origin_is_refused(post, headers):
    assert post("/pause", headers=headers).status_code == 403
    assert not pause.is_paused()


def test_referer_from_dashboard_is_accepted(post):
    assert post("/pause", headers={"Referer": "http://127.0.0.1:8000/status"}).status_code == 303


@pytest.mark.parametrize("token", ["", "wrong"])
def test_bad_csrf_token_is_refused(client, token):
    r = client.post("/pause", data={"csrf": token}, headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 403 and not pause.is_paused()


def test_missing_csrf_field_is_refused(client):
    r = client.post("/pause", headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code == 403 and not pause.is_paused()
