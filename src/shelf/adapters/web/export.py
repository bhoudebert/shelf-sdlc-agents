"""Downloading a work as one Markdown file, for debugging it somewhere else."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.export import ExportStep, WorkExport, filename, render
from shelf.domain.guard import StoppedCall
from shelf.domain.model import WorkId
from shelf.domain.result import Ok
from shelf.domain.story import request_in
from shelf.domain.usage import summarize


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


def router(web: Web) -> APIRouter:
    """The download route: it gives what the page shows, to the people who may see the page."""
    routes = APIRouter()

    @routes.get("/work/{work_id}/export")
    async def export(session: Annotated[Session, Depends(web.signed_in)], work_id: str) -> Response:
        work = await web.visible_work(session, work_id)
        item = views.item_view(work)
        number = views.pull_request_of(work.pull_request_url)
        story = None
        request = ""
        if web.deps.conversations is not None and number is not None:
            try:
                story = await web.deps.conversations.read(work.repo, number)
                request, _ = request_in(await web.deps.conversations.description(work.repo, number))
            except Exception:  # noqa: BLE001 - a part that cannot be read is said in the file; the rest is delivered
                story = None
        documents = None
        if web.deps.documents is not None:
            try:
                documents = await web.deps.documents.read(work.repo, work.id)
            except Exception:  # noqa: BLE001 - the same
                documents = None
        usage = summarize(await web.deps.runner.usage(WorkId(work_id)))
        guard = await _guard_calls(web)
        runs = await web.deps.run_records.read(work_id) if web.deps.run_records is not None else None
        started = min((at for _, at in work.times if at), default="")
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
        steps = [ExportStep(step.label, step.state, step.at) for step in views.timeline(work)]
        text = render(
            WorkExport(
                work_id=work_id,
                facts=facts,
                steps=steps,
                request=request,
                conversation=story,
                documents=documents,
                usage=usage,
                generated=datetime.now(UTC).strftime("%d %b %Y %H:%M UTC"),
                guard=guard,
                started=started,
                runs=runs,
                ended=work.updated_at if work.outcome else "",
            )
        )
        return Response(
            text,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename(work_id)}"', "Cache-Control": "no-store"},
        )

    return routes
