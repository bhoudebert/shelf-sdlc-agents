"""Starting work: pick a repository and a starting point, say what you want."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.application.errors import Invalid, NotAllowed, NotFound, Refusal
from shelf.application.work import start_work
from shelf.domain.config import InvalidConfigError
from shelf.domain.model import RepoRef, WorkRequest
from shelf.domain.pipeline import EntryPoint
from shelf.domain.result import Err, Ok


def explain(refusal: Refusal) -> tuple[str, int]:
    """What to tell the person, and the HTTP status, for a refused start."""
    match refusal:
        case Invalid(reason):
            return reason, 422
        case NotFound():
            return "That repository is not available to you.", 404
        case NotAllowed(reason):
            return reason, 403


def router(web: Web) -> APIRouter:
    """The start routes."""
    routes = APIRouter()
    deps = web.deps
    guarded = [Depends(web.same_origin)]

    async def start_form(request: Request, session: Session, *, error: str = "", status: int = 200) -> Response:
        repos = sorted(r.full_name for r in await deps.forge.repositories(session.user_token))
        response = web.render(
            request,
            "start.html",
            session,
            repos=repos,
            entries=views.entry_options(frozenset(EntryPoint)),
            install_url=deps.settings.install_url,
            error=error,
        )
        response.status_code = status
        return response

    @routes.get("/start", response_class=HTMLResponse)
    async def start_page(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> Response:
        return await start_form(request, session)

    @routes.post("/start", dependencies=guarded)
    async def start(
        request: Request,
        session: Annotated[Session, Depends(web.signed_in)],
        repo: Annotated[str, Form()],
        entry: Annotated[str, Form()],
        text: Annotated[str, Form()] = "",
        pull_request: Annotated[str, Form()] = "",
        reference: Annotated[str, Form()] = "",
        context: Annotated[str, Form()] = "",
    ) -> Response:
        try:
            asked = WorkRequest(
                RepoRef.parse(repo),
                session.identity.login,
                EntryPoint(entry),
                text,
                int(pull_request) if pull_request.strip() else None,
            )
        except ValueError:
            return await start_form(request, session, error="Choose a repository and a starting point.", status=422)
        try:
            result = await start_work(
                deps.runner,
                deps.forge,
                deps.configs,
                user_token=session.user_token,
                request=asked,
                references=deps.references,
                reference=reference,
                context_sources=deps.context_sources,
                context=context,
            )
        except InvalidConfigError as error:
            return await start_form(request, session, error=f"The repository's .shelf/config.toml: {error}", status=422)
        match result:
            case Ok(work_id):
                return RedirectResponse(f"/work/{work_id}", status_code=303)
            case Err(refusal):
                message, status = explain(refusal)
                return await start_form(request, session, error=message, status=status)

    return routes
