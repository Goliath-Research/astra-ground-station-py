"""Operator web application.

FastAPI replaces the Delphi configurator and test manager. ``GET /health``
and ``GET /`` stay open. ``/api`` is the JSON API and requires
``ASTRA_WEB_TOKEN``. The page at ``/`` is the configurator.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from astra import __version__
from astra.web.api import router
from astra.web.settings import WebSettings, web_settings_from_env

STATIC_DIR = Path(__file__).resolve().parent / "static"

WEB_STACK = "fastapi"


def create_app(settings: WebSettings | None = None) -> FastAPI:
    """Return the operator application.

    ``settings`` overrides the environment. Tests pass a token and a database
    URL here so they do not depend on the process environment.
    """
    resolved = web_settings_from_env() if settings is None else settings
    app = FastAPI(title="Astra ground station", version=__version__)
    app.state.web_settings = resolved
    app.state.stream = {}
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    index = STATIC_DIR / "index.html"

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(index)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
