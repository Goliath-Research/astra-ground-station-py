"""Operator web application.

FastAPI replaces the Delphi configurator and test manager. ``GET /health``
stays open for the process check. ``/api`` is the JSON API and requires
``ASTRA_WEB_TOKEN``. HTML screens are a later slice of phase 6.
"""

from fastapi import FastAPI

from astra import __version__
from astra.web.api import router
from astra.web.settings import WebSettings, web_settings_from_env

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

    return app
