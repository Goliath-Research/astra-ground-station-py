from fastapi.routing import APIRoute

from astra.web import WEB_STACK, create_app
from astra.web.__main__ import main


def test_web_app_is_a_fastapi_placeholder() -> None:
    assert WEB_STACK == "fastapi"
    app = create_app()
    paths = {route.path for route in app.routes if isinstance(route, APIRoute)}
    assert "/health" in paths
    assert main(["--check"]) == 0
