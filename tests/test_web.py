import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from astra.web import WEB_STACK, create_app
from astra.web.__main__ import main
from astra.web.settings import WebSettings


def _function_body(script: str, name: str) -> str:
    """Return one top-level function, including its braces."""
    marker = f"function {name}("
    start = script.find(marker)
    assert start >= 0
    open_brace = script.find("{", start)
    assert open_brace >= 0
    depth = 0
    for index in range(open_brace, len(script)):
        char = script[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return script[open_brace : index + 1]
    raise AssertionError(name)


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
        "Hardware",
        "Transformations",
        "Devices",
        "Servers",
        "Send / Rate",
        "Tests",
    ):
        assert label in page.text
    assert 'id="server-password" type="password"' in page.text
    assert 'id="token" type="password"' in page.text
    assert 'id="duplicate-node"' in page.text
    assert "Simulink CSV" in page.text
    assert "Mapping CSV" in page.text
    assert "OPC UA nodes" in page.text
    assert 'id="field-description"' in page.text
    assert 'id="field-in-sequence"' in page.text
    assert 'id="field-transformation"' in page.text
    assert 'id="field-record"' in page.text
    assert 'id="add-record"' in page.text
    assert 'id="print-hardware"' in page.text
    assert 'id="save-pin"' in page.text
    assert 'value="8">Hardware' in page.text
    assert 'value="9">Area' in page.text
    assert 'value="10">Board' in page.text
    assert "In sequence" in page.text
    assert script.status_code == 200
    assert style.status_code == 200
    assert "console.log" not in script.text
    assert "password_set" in script.text
    assert 'testAction(row.id, "start", "Start")' in script.text
    assert 'testAction(row.id, "stop", "Stop")' in script.text
    save_field = _function_body(script.text, "saveField")
    assert "fieldEditorBody()" in save_field
    editor = _function_body(script.text, "fieldEditorBody")
    for column in (
        "description",
        "in_sequence",
        "transformation_id",
        "initial_value",
        "short_name",
    ):
        assert column in editor
    clear_field = _function_body(script.text, "clearFieldForm")
    assert "field-description" in clear_field
    assert "field-in-sequence" in clear_field
    assert "field-transformation" in clear_field


def test_sign_out_clears_editor_ids() -> None:
    app = create_app()
    with TestClient(app) as client:
        script = client.get("/static/app.js")
    assert script.status_code == 200
    sign_out = _function_body(script.text, "signOut")
    for snippet in (
        "state.testId = null",
        "state.logPacketId = null",
        "clearPacketForm()",
        "clearFieldForm()",
        "clearPinForm()",
        "clearDeviceForm()",
        "clearServerForm()",
        '$("test-name").value = ""',
        '$("test-server").value = ""',
        '$("record-name").value = ""',
        '$("record-description").value = ""',
        '$("record-short-name").value = ""',
    ):
        assert snippet in sign_out
    assert "state.fieldId = null" in _function_body(script.text, "clearFieldForm")
    assert "state.connectionId = null" in _function_body(script.text, "clearPinForm")
    assert "state.deviceId = null" in _function_body(script.text, "clearDeviceForm")
    assert "state.serverId = null" in _function_body(script.text, "clearServerForm")


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
