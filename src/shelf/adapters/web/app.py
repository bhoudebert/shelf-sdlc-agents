"""The web application: sign in, board, start, work page, decisions, webhooks."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shelf.adapters.web import auth, board, hooks, start, work
from shelf.adapters.web.context import ASSETS, Web, WebDeps


def create_app(deps: WebDeps) -> FastAPI:
    """Build the application over ``deps``: every route calls a use case or a port, none holds a rule."""
    app = FastAPI(title="shelf-sdlc", docs_url=None, redoc_url=None, openapi_url=None)
    web = Web(deps)
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")
    for build in (auth.router, board.router, start.router, work.router, hooks.router):
        app.include_router(build(web))
    return app
