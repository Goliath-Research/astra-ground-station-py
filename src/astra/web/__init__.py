"""Operator web application.

FastAPI replaces the Delphi configurator and test manager. The only route
today is a health check. CRUD screens are phase 6.
"""

from fastapi import FastAPI

from astra import __version__

WEB_STACK = "fastapi"


def create_app() -> FastAPI:
    """Return the placeholder application."""
    app = FastAPI(title="Astra ground station", version=__version__)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "placeholder"}

    return app
