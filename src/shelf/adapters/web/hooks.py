"""GitHub webhooks and the health check."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from shelf.adapters.web.context import Web
from shelf.adapters.web.webhook import Closed, Commented, interpret, valid_signature
from shelf.adapters.web.webhook_log import Result
from shelf.application.work import decide_work
from shelf.domain.access import may_act_from_github
from shelf.domain.result import Err, Ok

log = logging.getLogger("shelf.webhook")


def router(web: Web) -> APIRouter:
    """The webhook receiver."""
    routes = APIRouter()
    deps = web.deps

    @routes.post("/api/github/webhook")
    async def webhook(request: Request) -> Response:
        event = request.headers.get("x-github-event", "")
        delivery = request.headers.get("x-github-delivery", "")
        body = await request.body()
        if not valid_signature(deps.settings.webhook_secret, body, request.headers.get("x-hub-signature-256")):
            web.webhooks.record(event, Result.BAD_SIGNATURE, delivery=delivery)
            log.warning("webhook %s refused: the signature does not match GITHUB_WEBHOOK_SECRET", event)
            raise HTTPException(status_code=401, detail="bad signature")
        payload = json.loads(body)
        repo = str(payload.get("repository", {}).get("full_name", ""))
        meaning = interpret(event, payload)
        match meaning:
            case Closed(work_id, merged):
                await deps.runner.pull_request_closed(work_id, merged=merged)
                web.webhooks.record(
                    event, Result.APPLIED, f"{work_id} {'merged' if merged else 'closed'}", repo=repo, delivery=delivery
                )
                log.info("webhook %s: %s %s", event, work_id, "merged" if merged else "closed")
            case Commented(work_id, login, kind, note, association, owner) if not may_act_from_github(
                deps.rules, login, association, owner
            ):
                web.webhooks.record(event, Result.REFUSED, f"{login} is not on the access list: ignored")
                log.warning("webhook %s: %s on %s ignored: not on the access list", event, login, work_id)
            case Commented(work_id, login, kind, note):
                result = await decide_work(
                    deps.runner, deps.configs, deps.rules, work_id=work_id, login=login, kind=kind, note=note
                )
                match result:
                    case Ok():
                        web.webhooks.record(
                            event, Result.APPLIED, f"{login} decided {kind} on {work_id}", repo=repo, delivery=delivery
                        )
                        log.info("webhook %s: %s decided %s on %s", event, login, kind, work_id)
                    case Err(refusal):
                        web.webhooks.record(
                            event, Result.REFUSED, f"{login} on {work_id}: {refusal}", repo=repo, delivery=delivery
                        )
                        log.warning("webhook %s: %s on %s not applied: %s", event, login, work_id, refusal)
            case None:
                web.webhooks.record(event, Result.IGNORED, repo=repo, delivery=delivery)
        return Response(status_code=202)

    @routes.get("/healthz")
    async def health() -> dict[str, str]:
        last = web.webhooks.last()
        return {
            "status": "ok",
            "revision": web.deps.settings.revision,
            "webhook": f"{last.event}:{last.result}" if last else "none yet",
        }

    return routes
