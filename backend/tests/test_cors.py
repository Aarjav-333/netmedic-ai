"""Origin policy: exact origins plus an optional full-matched regex, applied to REST and WS alike."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

# The pattern docker-compose ships: loopback / private / .local hosts on the dashboard port.
PRIVATE_HOSTS = (
    r"https?://(localhost|\[::1\]|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2[0-9]|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|[A-Za-z0-9-]+\.local):3000"
)


def make_client(**overrides) -> TestClient:
    """A client over an app built with explicit settings - no global patching, so the
    settings survive into the lifespan if a test enters the client as a context manager."""
    return TestClient(create_app(Settings(auto_tick=False, **overrides)))


def allowed(client: TestClient, origin: str) -> bool:
    res = client.options("/api/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    return res.headers.get("access-control-allow-origin") == origin


def test_default_origins_cover_loopback_only():
    client = make_client()
    assert allowed(client, "http://localhost:3000")
    assert allowed(client, "http://127.0.0.1:3000")
    assert allowed(client, "http://[::1]:3000")
    assert not allowed(client, "http://evil.example")
    # No regex by default: a LAN address needs an explicit opt-in.
    assert not allowed(client, "http://192.168.1.10:3000")


def test_origin_regex_is_full_matched():
    client = make_client(cors_origins="", cors_origin_regex=r"https?://[^/]+:3000")
    assert allowed(client, "http://192.168.1.10:3000")
    assert not allowed(client, "http://192.168.1.10:30001")  # fullmatch, not prefix
    assert not allowed(client, "http://192.168.1.10:8000")


def test_shipped_regex_allows_private_hosts_but_not_the_public_internet():
    client = make_client(cors_origins="", cors_origin_regex=PRIVATE_HOSTS)
    for origin in ("http://192.168.1.10:3000", "http://10.0.0.5:3000", "http://172.16.0.1:3000", "https://demo.local:3000"):
        assert allowed(client, origin), origin
    # The API has no auth, so a page served anywhere on the dashboard port must not reach it.
    for origin in ("http://evil.example:3000", "http://1.2.3.4:3000", "http://172.32.0.1:3000"):
        assert not allowed(client, origin), origin


def test_settings_origin_check_matches_middleware():
    settings = Settings(auto_tick=False, cors_origins="http://localhost:3000", cors_origin_regex=PRIVATE_HOSTS)
    assert settings.is_allowed_origin("http://localhost:3000")
    assert settings.is_allowed_origin("http://10.1.2.3:3000")
    assert not settings.is_allowed_origin("http://evil.example:3000")
    assert not Settings(auto_tick=False, cors_origins="").is_allowed_origin("http://localhost:3000")


@pytest.mark.parametrize("origin", ["http://evil.example:3000", "http://1.2.3.4:3000"])
def test_websocket_rejects_disallowed_origin(origin):
    """The stream carries more than any REST route; it must honour the same allow-list."""
    from starlette.websockets import WebSocketDisconnect

    client = make_client(cors_origin_regex=PRIVATE_HOSTS)
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/network", headers={"Origin": origin}) as ws:
            ws.receive_json()
    assert excinfo.value.code == 1008


def test_websocket_accepts_allowed_and_header_less_clients(engine):
    client = make_client(cors_origin_regex=PRIVATE_HOSTS)
    with client.websocket_connect("/ws/network", headers={"Origin": "http://localhost:3000"}) as ws:
        assert ws.receive_json()["type"] == "state"
    # Non-browser clients (curl, probes, tests) send no Origin and could forge one anyway.
    with client.websocket_connect("/ws/network") as ws:
        assert ws.receive_json()["type"] == "state"
