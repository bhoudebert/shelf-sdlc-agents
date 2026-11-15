"""Downloading a work as one Markdown file, for debugging it somewhere else."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.export import ExportStep, WorkExport, filename, render
from shelf.domain.guard import StoppedCall
from shelf.domain.model import RepoRef, WorkId
from shelf.domain.result import Ok
from shelf.domain.runlog import RunRecord
from shelf.domain.story import Message, request_in
from shelf.domain.usage import StepUsage, summarize

HTTP_NOT_FOUND = 404
ARCHIVED = (
    "the workflow engine no longer holds this work (it forgets a finished one after 24 hours), so its steps, outcome "
    "and stops are not known. This file is built from the run records, the work's branch and its pull request."
)


async def _guard_calls(web: Web) -> tuple[StoppedCall, ...] | None:
    """The calls the guard flagged, newest first, or ``None`` when it cannot be read: never an error."""
    reader = web.deps.guard
    if reader is None:
        return None
    try:
        result = await reader.report()
    except Exception:  # noqa: BLE001 - the file is still delivered, and says the guard could not be read
        return None
    return result.value.recent if isinstance(result, Ok) else None


async def _story(web: Web, repo: RepoRef, number: int | None) -> tuple[Sequence[Message] | None, str]:
    """The conversation of the pull request and the request it began with; ``None`` when it cannot be read."""
    if web.deps.conversations is None or number is None:
        return None, ""
    try:
        story = await web.deps.conversations.read(repo, number)
        request, _ = request_in(await web.deps.conversations.description(repo, number))
    except Exception:  # noqa: BLE001 - a part that cannot be read is said in the file; the rest is delivered
        return None, ""
    return story, request


async def _documents(web: Web, repo: RepoRef, work_id: str) -> Mapping[str, str] | None:
    if web.deps.documents is None:
        return None
    try:
        return await web.deps.documents.read(repo, WorkId(work_id))
    except Exception:  # noqa: BLE001 - the same
        return None


def _reply(text: str, work_id: str) -> Response:
    return Response(
        text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename(work_id)}"', "Cache-Control": "no-store"},
    )


def _step_usages(runs: Sequence[RunRecord]) -> tuple[StepUsage, ...]:
    """What each run used, as the steps of a work, for a work the engine can no longer be asked about."""
    return tuple(StepUsage(run.phase, run.attempt, run.role, run.usage) for run in runs)


async def _archived(web: Web, session: Session, work_id: str) -> Response:
    """The file of a work the engine has forgotten, from the records, the branch and the pull request."""
    runs: Sequence[RunRecord] = []
    if web.deps.run_records is not None:
        runs = await web.deps.run_records.read(work_id)
    if not runs or not runs[0].repo:
        raise HTTPException(status_code=404, detail="no such work")
    try:
        repo = RepoRef.parse(runs[0].repo)
    except ValueError:
        raise HTTPException(status_code=404, detail="no such work") from None
    visible = {r.full_name for r in await web.deps.forge.repositories(session.user_token)}
    if repo.full_name not in visible and not web.is_admin(session):
        raise HTTPException(status_code=404, detail="no such work")
    number = None
    if web.deps.conversations is not None:
        try:
            number = await web.deps.conversations.pull_request_of(repo, f"shelf/{work_id}")
        except Exception:  # noqa: BLE001 - no pull request found is said in the file
            number = None
    story, request = await _story(web, repo, number)
    facts = [
        ("Repository", repo.full_name),
        ("Requested by", runs[0].requester),
        ("Began as", runs[0].entry),
        ("Pull request", f"https://github.com/{repo.full_name}/pull/{number}" if number else ""),
        ("Archived", ARCHIVED),
    ]
    text = render(
        WorkExport(
            work_id=work_id,
            facts=facts,
            steps=[],
            request=request,
            conversation=story,
            documents=await _documents(web, repo, work_id),
            usage=summarize(_step_usages(runs)),
            generated=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"),
            guard=await _guard_calls(web),
            started=runs[0].started,
            ended=runs[-1].ended,
            runs=runs,
        )
    )
    return _reply(text, work_id)


def router(web: Web) -> APIRouter:
    """The download route: it gives what the page shows, to the people who may see the page."""
    routes = APIRouter()

    @routes.get("/work/{work_id}/export")
    async def export(session: Annotated[Session, Depends(web.signed_in)], work_id: str) -> Response:
        try:
            work = await web.visible_work(session, work_id)
        except HTTPException as missing:
            if missing.status_code != HTTP_NOT_FOUND:
                raise
            return await _archived(web, session, work_id)
        item = views.item_view(work)
        story, request = await _story(web, work.repo, views.pull_request_of(work.pull_request_url))
        runs = await web.deps.run_records.read(work_id) if web.deps.run_records is not None else None
        facts = [
            ("Repository", item.repo),
            ("Title", item.title),
            ("Requested by", item.requester),
            ("Began as", item.entry),
            ("Phase", item.phase),
            ("Outcome", item.outcome or "still running"),
            ("Waiting for", item.waiting),
            ("Pull request", item.pull_request_url),
            ("Does without a person", item.unattended),
            ("Reviews", item.review_depths),
            ("Reads as reference", ", ".join(item.context)),
            ("Detail", " ".join(item.detail.split())[:600]),
        ]
        text = render(
            WorkExport(
                work_id=work_id,
                facts=facts,
                steps=[ExportStep(step.label, step.state, step.at) for step in views.timeline(work)],
                request=request,
                conversation=story,
                documents=await _documents(web, work.repo, work_id),
                usage=summarize(await web.deps.runner.usage(WorkId(work_id))),
                generated=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"),
                guard=await _guard_calls(web),
                started=min((at for _, at in work.times if at), default=""),
                runs=runs,
                ended=work.updated_at if work.outcome else "",
            )
        )
        return _reply(text, work_id)

    return routes
