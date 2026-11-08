"""Looking at a piece of work and deciding for it."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.application.work import decide_work
from shelf.domain.model import WorkId
from shelf.domain.result import Ok
from shelf.domain.work import DecisionKind

type Panel = tuple[views.ItemView, list[views.TimelineStep], list[views.DecisionOption]]


def router(web: Web) -> APIRouter:
    """The work page and decision routes."""
    routes = APIRouter()
    guarded = [Depends(web.same_origin)]
    deps = web.deps

    async def panel_of(session: Session, work_id: str) -> Panel:
        work = await deps.runner.view(WorkId(work_id))
        visible = {r.full_name for r in await deps.forge.repositories(session.user_token)}
        if work is None or work.repo.full_name not in visible:
            raise HTTPException(status_code=404, detail="no such work")
        return views.item_view(work), views.timeline(work), views.decision_options(work.waiting_for)

    @routes.get("/work/{work_id}", response_class=HTMLResponse)
    async def page(request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str) -> Response:
        item, timeline, decisions = await panel_of(session, work_id)
        return web.render(request, "work.html", session, item=item, timeline=timeline, decisions=decisions, flash="")

    @routes.get("/work/{work_id}/panel", response_class=HTMLResponse)
    async def panel(request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str) -> Response:
        item, timeline, decisions = await panel_of(session, work_id)
        return web.render(
            request, "_work_panel.html", session, item=item, timeline=timeline, decisions=decisions, flash=""
        )

    @routes.post("/work/{work_id}/decide", dependencies=guarded)
    async def decide(
        request: Request,
        session: Annotated[Session, Depends(web.signed_in)],
        work_id: str,
        kind: Annotated[str, Form()],
        note: Annotated[str, Form()] = "",
    ) -> Response:
        item, timeline, decisions = await panel_of(session, work_id)
        try:
            decision = DecisionKind(kind)
        except ValueError:
            raise HTTPException(status_code=422, detail="unknown decision") from None
        result = await decide_work(
            deps.runner,
            deps.configs,
            deps.rules,
            work_id=WorkId(work_id),
            login=session.identity.login,
            kind=decision,
            note=note,
        )
        accepted = isinstance(result, Ok)
        response = web.render(
            request,
            "_work_panel.html",
            session,
            item=item,
            timeline=timeline,
            decisions=decisions,
            flash="Decision sent." if accepted else "You may not decide this here.",
        )
        response.status_code = 200 if accepted else 403
        return response

    return routes
