"""CORS configuration: exact origins plus an optional full-matched regex."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client(**overrides) -> TestClient:
    settings = Settings(auto_tick=False, **overrides)
    import app.main as main_module

    original = main_module.get_settings
    main_module.get_settings = lambda: settings  # type: ignore[assignment]
    try:
        return TestClient(create_app())
    finally:
        main_module.get_settings = original


def allowed(client: TestClient, origin: str) -> bool:
    res = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    return res.headers.get("access-control-allow-origin") == origin


def test_default_origins_include_localhost_and_loopback():
    client = make_client()
    assert allowed(client, "http://localhost:3000")
    assert allowed(client, "http://127.0.0.1:3000")
    assert not allowed(client, "http://evil.example")


def test_origin_regex_is_full_matched():
    client = make_client(cors_origins="", cors_origin_regex=r"^https?://[^/]+:3000")
    assert allowed(client, "http://192.168.1.10:3000")
    assert allowed(client, "https://demo-box.local:3000")
    assert not allowed(client, "http://192.168.1.10:30001")
    assert not allowed(client, "http://192.168.1.10:8000")
