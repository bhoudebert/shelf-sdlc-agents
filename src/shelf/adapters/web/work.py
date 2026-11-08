"""Looking at a piece of work and deciding for it."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.application.work import decide_work
from shelf.domain.config import InvalidConfigError
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
        work = await web.visible_work(session, work_id)
        return views.item_view(work), views.timeline(work), views.decision_options(work.waiting_for)

    @routes.get("/work/{work_id}", response_class=HTMLResponse)
    async def page(request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str) -> Response:
        item, timeline, decisions = await panel_of(session, work_id)
        return web.render(
            request,
            "work.html",
            session,
            item=item,
            timeline=timeline,
            decisions=decisions,
            flash="",
            version=views.version_of(item, timeline, decisions),
            temporal_link=web.temporal_link(work_id) if web.is_admin(session) else "",
        )

    @routes.get("/work/{work_id}/panel", response_class=HTMLResponse)
    async def panel(
        request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str, v: str = ""
    ) -> Response:
        item, timeline, decisions = await panel_of(session, work_id)
        version = views.version_of(item, timeline, decisions)
        if v == version:  # nothing new: answer with no content so the page is left exactly as it is
            return Response(status_code=204)
        return web.render(
            request,
            "_work_panel.html",
            session,
            item=item,
            timeline=timeline,
            decisions=decisions,
            flash="",
            version=version,
        )

    async def outcome_of(session: Session, work_id: str, decision: DecisionKind, note: str) -> tuple[str, int]:
        """Deliver the decision; say what happened and with which HTTP status."""
        try:
            result = await decide_work(
                deps.runner,
                deps.configs,
                deps.rules,
                work_id=WorkId(work_id),
                login=session.identity.login,
                kind=decision,
                note=note,
            )
        except InvalidConfigError as error:
            return f"The repository's configuration is invalid: {error}", 422
        if isinstance(result, Ok):
            return "Decision sent.", 200
        return "You may not decide this here.", 403

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
        flash, status = await outcome_of(session, work_id, decision, note)
        response = web.render(
            request, "_work_panel.html", session, item=item, timeline=timeline, decisions=decisions, flash=flash
        )
        response.status_code = status
        return response

    return routes
