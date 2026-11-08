"""GitHub webhooks and the health check."""

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from shelf.adapters.web.context import Web
from shelf.adapters.web.webhook import Closed, Commented, interpret, valid_signature
from shelf.application.work import decide_work


def router(web: Web) -> APIRouter:
    """The webhook receiver."""
    routes = APIRouter()
    deps = web.deps

    @routes.post("/api/github/webhook")
    async def webhook(request: Request) -> Response:
        body = await request.body()
        if not valid_signature(deps.settings.webhook_secret, body, request.headers.get("x-hub-signature-256")):
            raise HTTPException(status_code=401, detail="bad signature")
        meaning = interpret(request.headers.get("x-github-event", ""), json.loads(body))
        match meaning:
            case Closed(work_id, merged):
                await deps.runner.pull_request_closed(work_id, merged=merged)
            case Commented(work_id, login, kind, note):
                await decide_work(
                    deps.runner, deps.configs, deps.rules, work_id=work_id, login=login, kind=kind, note=note
                )
            case None:
                pass
        return Response(status_code=202)

    @routes.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok", "revision": web.deps.settings.revision}

    return routes
