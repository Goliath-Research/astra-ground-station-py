import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astra.web import WEB_STACK, create_app
from astra.web.__main__ import main
from astra.web.settings import WebSettings


def _paths(app: FastAPI) -> set[str]:
    """Collect route paths, including routers FastAPI keeps nested."""
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str):
            paths.add(path)
        original = getattr(route, "original_router", None)
        if original is None:
            continue
        for child in original.routes:
            child_path = getattr(child, "path", None)
            if isinstance(child_path, str):
                paths.add(child_path)
    return paths


def test_web_app_exposes_health_and_the_config_api() -> None:
    assert WEB_STACK == "fastapi"
    app = create_app()
    paths = _paths(app)
    assert "/health" in paths
    assert "/api/tree" in paths
    assert "/api/servers" in paths
    assert main(["--check"]) == 0
    with TestClient(app) as client:
        health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}


def test_operator_page_lists_the_configurator_screens() -> None:
    app = create_app()
    with TestClient(app) as client:
        page = client.get("/")
        script = client.get("/static/app.js")
        style = client.get("/static/app.css")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    for label in (
        "Configuration tree",
        "Packet",
        "Fields",
        "Mappings",
        "Transformations",
        "Devices",
        "Servers",
        "Send / Rate",
    ):
        assert label in page.text
    assert 'id="server-password" type="password"' in page.text
    assert 'id="token" type="password"' in page.text
    assert 'id="duplicate-node"' in page.text
    assert "Simulink CSV" in page.text
    assert "Mapping CSV" in page.text
    assert "OPC UA nodes" in page.text
    assert script.status_code == 200
    assert style.status_code == 200
    assert "console.log" not in script.text
    assert "password_set" in script.text


def test_api_is_closed_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASTRA_WEB_TOKEN", raising=False)
    app = create_app()
    with TestClient(app) as client:
        denied = client.get("/api/tree")
        health = client.get("/health")
    assert denied.status_code == 503
    assert denied.json() == {"detail": "ASTRA_WEB_TOKEN is not set"}
    assert health.status_code == 200


def test_short_token_is_rejected_and_not_echoed(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "short-secret"
    monkeypatch.setenv("ASTRA_WEB_TOKEN", secret)
    app = create_app()
    with TestClient(app) as client:
        denied = client.get("/api/servers", headers={"Authorization": f"Bearer {secret}"})
    assert denied.status_code == 503
    assert secret not in denied.text
    assert denied.json()["detail"] == "ASTRA_WEB_TOKEN must be at least 16 characters"


def test_wrong_bearer_token_is_unauthorized() -> None:
    presented = "presented-token-value"
    app = create_app(
        WebSettings(
            database_url=None,
            token="expected-token-value",
            database_error="DATABASE_URL is not set",
            token_error=None,
        )
    )
    with TestClient(app) as client:
        denied = client.get("/api/tree", headers={"Authorization": f"Bearer {presented}"})
    assert denied.status_code == 401
    assert denied.json() == {"detail": "unauthorized"}
    assert presented not in denied.text
    assert "expected-token-value" not in denied.text
