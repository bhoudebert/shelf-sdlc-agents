"""Temporal's own interface, served under ``/temporal`` behind shelf's sign-in, for administrators only.

Temporal's UI has no login of its own and can signal or end any workflow, so it is never exposed directly: this proxy
is the only way in. It requires a signed-in administrator, is read-only unless the operator allows writes (queries are
always allowed, they are how you inspect a workflow), and never forwards shelf's cookies upstream.
"""

import re
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session

PREFIX = "/temporal"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_QUERY = re.compile(r"/api/v1/namespaces/[^/]+/workflows/[^/]+/(runs/[^/]+/)?query(/(?!\.\.?$)[^/]+)?$")
"""A workflow query, with or without the run and with or without the query's name (``__stack_trace``, a custom one)."""
HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)
NEVER_FORWARDED = frozenset(
    {"cookie", "authorization", "host", "origin", "referer", "content-length", "accept-encoding"}
)


def permitted(method: str, path: str, *, writable: bool) -> bool:
    """Whether the proxy lets this request through. Reading and querying always; changing things only when allowed."""
    if writable or method in SAFE_METHODS:
        return True
    return method == "POST" and bool(_QUERY.search(path))


def forwarded_headers(headers: dict[str, str]) -> dict[str, str]:
    """The request headers that go upstream: no cookies, no credentials, no hop-by-hop, no compression."""
    kept = {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP | NEVER_FORWARDED}
    return {**kept, "accept-encoding": "identity"}


def returned_headers(headers: httpx.Headers) -> dict[str, str]:
    """The response headers that come back, plus the ones that keep the page from being framed or cached."""
    kept = {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP | {"content-encoding", "set-cookie"}}
    return {**kept, "Cache-Control": "no-store", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer"}


async def _body(answer: httpx.Response) -> AsyncIterator[bytes]:
    if answer.is_stream_consumed:  # a transport that already buffered the answer
        yield answer.content
        return
    async for chunk in answer.aiter_raw():
        yield chunk


async def forward(web: Web, request: Request, path: str) -> Response:
    """Send the request to Temporal's interface and stream its answer back."""
    settings = web.deps.settings
    client = httpx.AsyncClient(
        base_url=settings.temporal_upstream, timeout=30, transport=web.deps.temporal_transport, follow_redirects=False
    )
    upstream = client.build_request(
        request.method,
        f"{PREFIX}/{path}",
        params=request.query_params,
        headers=forwarded_headers(dict(request.headers)),
        content=await request.body(),
    )
    try:
        answer = await client.send(upstream, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Temporal's interface did not answer") from error

    async def close() -> None:
        await answer.aclose()
        await client.aclose()

    return StreamingResponse(
        _body(answer),
        status_code=answer.status_code,
        headers=returned_headers(answer.headers),
        background=BackgroundTask(close),
    )


def router(web: Web) -> APIRouter:
    """The ``/temporal`` routes; they exist only when an upstream is configured."""
    routes = APIRouter()
    settings = web.deps.settings

    def administrator(session: Annotated[Session, Depends(web.signed_in)]) -> Session:
        if not web.is_admin(session):
            raise HTTPException(status_code=403, detail="administrators only")
        return session

    @routes.get(PREFIX)
    async def bare(_: Annotated[Session, Depends(administrator)]) -> Response:
        return RedirectResponse(f"{PREFIX}/", status_code=308)

    @routes.api_route(
        PREFIX + "/{path:path}",
        methods=["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"],
        include_in_schema=False,
    )
    async def proxy(request: Request, path: str, _: Annotated[Session, Depends(administrator)]) -> Response:
        if not settings.temporal_upstream:
            raise HTTPException(status_code=404, detail="Temporal's interface is not configured")
        if not permitted(request.method, request.url.path, writable=settings.temporal_writable):
            raise HTTPException(status_code=403, detail="read-only: changing workflows from here is turned off")
        if request.method not in SAFE_METHODS:
            web.same_origin(request)
        return await forward(web, request, path)

    return routes
