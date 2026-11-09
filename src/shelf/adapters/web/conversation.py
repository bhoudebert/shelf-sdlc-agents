"""The conversation of a piece of work, shown on its page as the agents and people write it."""

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.story import request_in

if TYPE_CHECKING:
    from collections.abc import Sequence

    from shelf.domain.story import Message


def router(web: Web) -> APIRouter:
    """The conversation route."""
    routes = APIRouter()

    @routes.get("/work/{work_id}/conversation", response_class=HTMLResponse)
    async def conversation(
        request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str, v: str = ""
    ) -> Response:
        work = await web.visible_work(session, work_id)
        number = views.pull_request_of(work.pull_request_url)
        story: Sequence[Message] = []
        failed = False
        description = ""
        if web.deps.conversations is not None and number is not None:
            try:
                story = await web.deps.conversations.read(work.repo, number)
                description = await web.deps.conversations.description(work.repo, number)
            except Exception:  # noqa: BLE001 - a GitHub hiccup must not break the page: say so, retry on the next poll
                failed = True
        items = views.feed(story)
        asked, ours = request_in(description)
        version = views.version_of([(i.speaker, i.when, len(str(i.html))) for i in items], failed, number, asked, ours)
        if v == version:  # nothing new: leave the page alone
            return Response(status_code=204)
        return web.render(
            request,
            "_conversation.html",
            session,
            work_id=work_id,
            items=items,
            failed=failed,
            request_html=views.render_markdown(asked) if asked else "",
            request_is_ours=ours,
            has_pull_request=number is not None,
            pull_request_url=work.pull_request_url,
            version=version,
        )

    return routes
