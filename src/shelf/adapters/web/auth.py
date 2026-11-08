"""Signing in with GitHub and out again."""

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from shelf.adapters.web.context import SESSION_COOKIE, SESSION_SECONDS, STATE_COOKIE, STATE_SECONDS, Web
from shelf.application.errors import NotAllowed
from shelf.application.sign_in import sign_in
from shelf.domain.result import Err, Ok


def router(web: Web) -> APIRouter:
    """The sign-in routes."""
    routes = APIRouter()
    settings = web.deps.settings

    @routes.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> Response:
        if web.current(request) is not None:
            return RedirectResponse("/board", status_code=303)
        return web.render(request, "login.html", None, login_url="/auth/login")

    @routes.get("/setup/installed")
    async def installed() -> Response:
        """Where GitHub sends a person after they install the App: on to their board (or to sign in first)."""
        return RedirectResponse("/board", status_code=303)

    @routes.get("/auth/login")
    async def login() -> Response:
        state = secrets.token_urlsafe(16)
        query = urlencode(
            {
                "client_id": settings.client_id,
                "redirect_uri": f"{settings.public_url.rstrip('/')}/auth/callback",
                "state": state,
            }
        )
        response = RedirectResponse(f"https://github.com/login/oauth/authorize?{query}", status_code=303)
        web.set_cookie(response, STATE_COOKIE, state, STATE_SECONDS)
        return response

    @routes.get("/auth/callback")
    async def callback(request: Request, code: str = "", state: str = "") -> Response:
        expected = web.read_cookie(request, STATE_COOKIE, STATE_SECONDS)
        if not code or expected is None or not secrets.compare_digest(expected, state):
            raise HTTPException(status_code=400, detail="the sign-in did not start here, or took too long")
        result = await sign_in(web.deps.forge, web.deps.rules, code)
        match result:
            case Err(NotAllowed(reason)):
                return web.render(request, "denied.html", None, reason=reason)
            case Ok(signed):
                session_id = web.deps.sessions.create(signed.identity, signed.user_token)
        response = RedirectResponse("/board", status_code=303)
        web.set_cookie(response, SESSION_COOKIE, session_id, SESSION_SECONDS)
        response.delete_cookie(STATE_COOKIE)
        return response

    @routes.post("/auth/logout", dependencies=[Depends(web.same_origin)])
    async def logout(request: Request) -> Response:
        web.deps.sessions.end(web.read_cookie(request, SESSION_COOKIE, SESSION_SECONDS))
        response = RedirectResponse("/", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        return response

    return routes
