"""The documents of a piece of work, shown on its page as they are written."""

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session

if TYPE_CHECKING:
    from collections.abc import Mapping


def router(web: Web) -> APIRouter:
    """The documents route."""
    routes = APIRouter()

    @routes.get("/work/{work_id}/documents", response_class=HTMLResponse)
    async def documents(
        request: Request, session: Annotated[Session, Depends(web.signed_in)], work_id: str, v: str = ""
    ) -> Response:
        work = await web.visible_work(session, work_id)
        found: Mapping[str, str] = {}
        failed = False
        if web.deps.documents is not None:
            try:
                found = await web.deps.documents.read(work.repo, work.id)
            except Exception:  # noqa: BLE001 - a GitHub hiccup must not break the page: say so, retry on the next poll
                failed = True
        version = views.version_of(sorted(found.items()), work.phase, failed)
        if v == version:  # nothing new: leave the page, and anything folded or selected in it, alone
            return Response(status_code=204)
        return web.render(
            request,
            "_documents.html",
            session,
            work_id=work_id,
            docs=views.document_views(found, work.phase),
            writes_documents=work.entry not in views.NO_DOCUMENTS,
            failed=failed,
            version=version,
        )

    return routes
