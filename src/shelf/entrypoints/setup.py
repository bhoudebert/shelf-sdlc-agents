"""First run: register the GitHub App in one click, then show the credentials to put in the environment.

Served only while the App is not configured. Nothing here signs anyone in or reaches GitHub on a person's behalf: the
person confirms on GitHub, and GitHub hands back a one-time code that is traded for the App's credentials.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shelf.adapters.github_app.manifest import convert, registration_form
from shelf.adapters.web.context import ASSETS

HttpClient = Callable[[], AbstractAsyncContextManager[httpx.AsyncClient]]


def create_setup_app(public_url: str, http_client: HttpClient | None = None) -> FastAPI:
    """The registration helper for the instance served at ``public_url``."""
    app = FastAPI(title="shelf-sdlc setup", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")
    templates = Jinja2Templates(directory=ASSETS / "templates")
    client_for: HttpClient = http_client or (lambda: httpx.AsyncClient(timeout=30))

    @app.get("/", response_class=HTMLResponse)
    async def start(request: Request) -> Response:
        return templates.TemplateResponse(
            request, "setup.html", {"user": None, "mode": "setup", "public_url": public_url}
        )

    @app.get("/setup/register", response_class=HTMLResponse)
    async def register() -> Response:
        return HTMLResponse(registration_form(public_url))

    @app.get("/setup/registered", response_class=HTMLResponse)
    async def registered(request: Request, code: str = "") -> Response:
        if not code:
            raise HTTPException(status_code=400, detail="GitHub did not send a registration code")
        async with client_for() as client:
            credentials = await convert(client, code)
        response = templates.TemplateResponse(
            request, "registered.html", {"user": None, "mode": "setup", "credentials": credentials}
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "setup"}

    return app
