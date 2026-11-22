"""What was settled without the person, shown on the work page before the merge (ADR 0021)."""

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.settled import settled_of
from shelf.domain.work import Reason

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from shelf.domain.story import Message


def router(web: Web) -> APIRouter:
    """The settled route."""
    routes = APIRouter()

    @routes.get("/work/{work_id}/settled", response_class=HTMLResponse)
    async def settled(
        request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str, v: str = ""
    ) -> Response:
        work = await web.visible_work(session, work_id)
        documents: Mapping[str, str] = {}
        story: Sequence[Message] = []
        failed = False
        number = views.pull_request_of(work.pull_request_url)
        try:
            if web.deps.documents is not None:
                documents = await web.deps.documents.read(work.repo, work.id)
            if web.deps.conversations is not None and number is not None:
                story = await web.deps.conversations.read(work.repo, number)
        except Exception:  # noqa: BLE001 - a GitHub hiccup must not break the page: say so, retry on the next poll
            failed = True
        found = settled_of(documents, story)
        at_the_merge = work.waiting_for is Reason.MERGE or work.outcome is not None
        version = views.version_of(found, failed, at_the_merge)
        if v == version:
            return Response(status_code=204)
        return web.render(
            request,
            "_settled.html",
            session,
            work_id=work_id,
            found=found,
            failed=failed,
            at_the_merge=at_the_merge,
            version=version,
        )

    return routes
