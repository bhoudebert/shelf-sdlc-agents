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
from shelf.domain.policy import Autonomy, DeadlockMode
from shelf.domain.result import Err, Ok
from shelf.domain.review import ReviewDepth
from shelf.ports.configs import RepoConfigs


def explain(refusal: Refusal) -> tuple[str, int]:
    """What to tell the person, and the HTTP status, for a refused start."""
    match refusal:
        case Invalid(reason):
            return reason, 422
        case NotFound():
            return "That repository is not available to you.", 404
        case NotAllowed(reason):
            return reason, 403


DEPTHS = (ReviewDepth.QUICK, ReviewDepth.STANDARD, ReviewDepth.THOROUGH)
"""The stops of a depth slider, from left to right."""
DEPTH_LEGEND = ("Quick: only what blocks", "Standard: the usual pass", "Thorough: edge cases, failures")

ANSWERS: tuple[tuple[str, str, str, str], ...] = (
    (
        DeadlockMode.ASK.value,
        "Ask me",
        "Stop and wait for me, with the two sides and what each costs.",
        "",
    ),
    (
        DeadlockMode.ARBITRATE_ASK.value,
        "An arbitrator decides; ask me only if it cannot",
        (
            "An agent reads the whole story and decides, in about a minute and for about the cost of one review. "
            "You are asked only for what only a person can decide."
        ),
        "",
    ),
    (
        DeadlockMode.ARBITRATE_GO.value,
        "An arbitrator decides; go on if it cannot",
        (
            "As above, but a spec or design point the arbitrator cannot decide goes on to the pull request, written "
            "down for you to read before you merge. A code review or a failing check that cannot be settled still "
            "asks you."
        ),
        "Default",
    ),
    (
        DeadlockMode.GO.value,
        "Do not settle it, go on",
        "The work goes on at once. What stayed open is posted on the pull request. Nobody arbitrates.",
        "",
    ),
)
SUMMARIES = {
    DeadlockMode.ASK.value: "A person decides, at once: the work waits for you when the two sides disagree for good.",
    DeadlockMode.ARBITRATE_ASK.value: (
        "The arbitrator decides first, in about a minute, for about the cost of one review. "
        "You are asked only when it says that only a person can decide."
    ),
    DeadlockMode.ARBITRATE_GO.value: (
        "The arbitrator decides first. A spec or design point it cannot settle goes on to the pull request, "
        "marked for you to check; a code review or a failing check it cannot settle asks you."
    ),
    DeadlockMode.GO.value: "Nobody decides: the work goes on and the open points are posted on the pull request.",
}


def depth_of(value: str) -> ReviewDepth | None:
    """The depth the form named (a name, or a stop of the slider), or ``None`` (the repository's own)."""
    try:
        return ReviewDepth(value)
    except ValueError:
        pass
    if value.strip() in ("0", "1", "2"):
        return DEPTHS[int(value)]
    return None


def mode_of(on_deadlock: str, stop_on_deadlock: str) -> DeadlockMode:
    """The answer the form gave to a disagreement; a form from before the question gives it by its old box."""
    try:
        return DeadlockMode(on_deadlock)
    except ValueError:
        return DeadlockMode.ASK if stop_on_deadlock else DeadlockMode.GO


def _form_parts() -> dict[str, object]:
    """What the autonomy section needs besides the choices: the four answers, their summaries, the depth legend."""
    return {"answers": ANSWERS, "summaries": SUMMARIES, "depth_legend": DEPTH_LEGEND}


def chosen_by(
    form: str,
    spec_approval: str,
    design_review: str,
    stop_on_deadlock: str,
    spec_review_depth: str = "",
    design_review_depth: str = "",
    on_deadlock: str = "",
) -> Autonomy | None:
    """What the form's two boxes, its question and its sliders say, or ``None`` when the form did not show them.

    A browser sends nothing for an unchecked box: the marker says the boxes were shown, so absent means unchecked.
    Every box is worded so that checked means more control.
    """
    if not form:
        return None
    mode = mode_of(on_deadlock, stop_on_deadlock)
    return Autonomy(
        spec_approval=bool(spec_approval),
        design_review=bool(design_review),
        proceed_on_deadlock=mode.goes_on,
        on_deadlock=mode,
        spec_review_depth=depth_of(spec_review_depth),
        design_review_depth=depth_of(design_review_depth),
    )


async def defaults_of(configs: RepoConfigs, repo: str) -> Autonomy:
    """What the repository's policy says about stops, or the strictest choice when it cannot be read."""
    try:
        return Autonomy.of((await configs.load(RepoRef.parse(repo))).policy)
    except (ValueError, InvalidConfigError):
        return Autonomy.strictest()


def router(web: Web) -> APIRouter:
    """The start routes."""
    routes = APIRouter()
    deps = web.deps
    guarded = [Depends(web.same_origin)]

    async def start_form(
        request: Request,
        session: Session,
        *,
        error: str = "",
        status: int = 200,
        repo: str = "",
        chosen: Autonomy | None = None,
    ) -> Response:
        repos = sorted(r.full_name for r in await deps.forge.repositories(session.user_token))
        selected = repo if repo in repos else (repos[0] if repos else "")
        response = web.render(
            request,
            "start.html",
            session,
            repos=repos,
            selected=selected,
            autonomy=chosen or (await defaults_of(deps.configs, selected) if selected else Autonomy.strictest()),
            **_form_parts(),
            entries=views.entry_options(frozenset(EntryPoint)),
            install_url=deps.settings.install_url,
            error=error,
        )
        response.status_code = status
        return response

    @routes.get("/start", response_class=HTMLResponse)
    async def start_page(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> Response:
        return await start_form(request, session)

    @routes.get("/start/autonomy", response_class=HTMLResponse)
    async def start_autonomy(
        request: Request, session: Annotated[Session, Depends(web.signed_in)], repo: str = ""
    ) -> Response:
        """The stops of one repository's policy, as the form shows them, when another repository is picked."""
        visible = {r.full_name for r in await deps.forge.repositories(session.user_token)}
        chosen = await defaults_of(deps.configs, repo) if repo in visible else Autonomy.strictest()
        return web.render(request, "_autonomy.html", session, autonomy=chosen, **_form_parts())

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
        autonomy_form: Annotated[str, Form()] = "",
        spec_approval: Annotated[str, Form()] = "",
        design_review: Annotated[str, Form()] = "",
        stop_on_deadlock: Annotated[str, Form()] = "",
        spec_review_depth: Annotated[str, Form()] = "",
        design_review_depth: Annotated[str, Form()] = "",
        on_deadlock: Annotated[str, Form()] = "",
    ) -> Response:
        chosen = chosen_by(
            autonomy_form,
            spec_approval,
            design_review,
            stop_on_deadlock,
            spec_review_depth,
            design_review_depth,
            on_deadlock,
        )
        try:
            asked = WorkRequest(
                RepoRef.parse(repo),
                session.identity.login,
                EntryPoint(entry),
                text,
                int(pull_request) if pull_request.strip() else None,
                autonomy=chosen,
            )
        except ValueError:
            return await start_form(
                request,
                session,
                error="Choose a repository and a starting point.",
                status=422,
                repo=repo,
                chosen=chosen,
            )
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
            return await start_form(
                request,
                session,
                error=f"The repository's .shelf/config.toml: {error}",
                status=422,
                repo=repo,
                chosen=chosen,
            )
        match result:
            case Ok(work_id):
                return RedirectResponse(f"/work/{work_id}", status_code=303)
            case Err(refusal):
                message, status = explain(refusal)
                return await start_form(request, session, error=message, status=status, repo=repo, chosen=chosen)

    return routes
