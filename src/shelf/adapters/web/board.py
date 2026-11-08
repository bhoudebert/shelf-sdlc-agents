"""The board: every piece of work the person can see, kept fresh with server-sent events."""

import asyncio
import hashlib
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.application.work import board

STREAM_INTERVAL = 2.0


def router(web: Web) -> APIRouter:
    """The board routes."""
    routes = APIRouter()

    async def items_for(session: Session) -> list[views.ItemView]:
        works = await board(
            web.deps.runner, web.deps.forge, user_token=session.user_token, everything=web.is_admin(session)
        )
        return [views.item_view(work) for work in works]

    @routes.get("/board", response_class=HTMLResponse)
    async def page(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> Response:
        repos = await web.deps.forge.repositories(session.user_token)
        return web.render(
            request,
            "board.html",
            session,
            items=await items_for(session),
            has_repos=bool(repos),
            install_url=web.deps.settings.install_url,
        )

    @routes.get("/board/items", response_class=HTMLResponse)
    async def items(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> Response:
        return web.render(request, "_board_items.html", session, items=await items_for(session))

    @routes.get("/board/stream")
    async def stream(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            last = ""
            while not await request.is_disconnected():
                fragment = web.templates.get_template("_board_items.html").render(items=await items_for(session))
                digest = hashlib.sha256(fragment.encode()).hexdigest()
                if digest != last:
                    last = digest
                    data = "\n".join(f"data: {line}" for line in fragment.splitlines() or [""])
                    yield f"event: board\n{data}\n\n"
                await asyncio.sleep(STREAM_INTERVAL)

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return routes
