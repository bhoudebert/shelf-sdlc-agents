"""The activities: the only place where the workflow touches the world, built from the ports they need."""

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from typing import Any

from temporalio import activity

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.workflow import (
    ANNOUNCE,
    ARBITRATE,
    CLOSE_PULL_REQUEST,
    OPEN_POINTS,
    POLL,
    PROGRESS,
    PUBLISH,
    READY,
    RECORD_ARBITRATION,
    RECORD_DECISION,
    RUN_STEP,
    STAGE,
)
from shelf.domain.decisions import DecisionRecord
from shelf.domain.pipeline import Phase
from shelf.domain.progress import Entry, Position, render_progress
from shelf.domain.roles import ROLES
from shelf.domain.stage import stage_of
from shelf.domain.story import open_points_comment
from shelf.domain.work import ArbitrationVerdict, AskPerson, DecisionKind, Outcome, Reason, RunStep
from shelf.ports.steps import PullRequests, StepRunner

HEARTBEAT_EVERY = 15.0
"""Seconds between two heartbeats of a running step; the workflow gives a step 60 seconds of silence."""


async def keep_alive(beat: Callable[[], None], every: float) -> None:
    """Call ``beat`` every ``every`` seconds until cancelled.

    A step cannot be trusted to speak up by itself while an agent thinks, a build runs or the CI is awaited.
    """
    while True:
        beat()
        await asyncio.sleep(every)


def _steps_activities(steps: StepRunner, pulls: PullRequests) -> Sequence[Callable[..., Any]]:
    """The activities that run a step, announce, publish and look at the pull request for a decision."""

    @activity.defn(name=RUN_STEP)
    async def run_step(step: wire.StepInput) -> wire.StepOutput:
        beating = asyncio.create_task(keep_alive(activity.heartbeat, HEARTBEAT_EVERY))
        try:
            result = await steps.run(
                wire.context_of(step.work), RunStep(Phase(step.phase), step.attempt, step.feedback, step.session)
            )
        finally:
            beating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beating
        return wire.output_of(result)

    @activity.defn(name=ARBITRATE)
    async def arbitrate(arbitration: wire.ArbitrationInput) -> wire.StepOutput:
        beating = asyncio.create_task(keep_alive(activity.heartbeat, HEARTBEAT_EVERY))
        try:
            result = await steps.arbitrate(
                wire.context_of(arbitration.work),
                Phase(arbitration.phase),
                arbitration.issues,
                arbitration.attempt,
            )
        finally:
            beating.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await beating
        return wire.output_of(result)

    @activity.defn(name=ANNOUNCE)
    async def announce(ask: wire.AskInput) -> None:
        await pulls.announce(wire.context_of(ask.work), AskPerson(Phase(ask.phase), Reason(ask.reason), ask.detail))

    @activity.defn(name=PUBLISH)
    async def publish(work: wire.WorkInput) -> str:
        context = wire.context_of(work)
        return await pulls.publish(context, await steps.title(context))

    @activity.defn(name=POLL)
    async def poll(work: wire.WorkInput) -> list[wire.EventDto]:
        events = await pulls.poll(wire.context_of(work))
        return [dto for event in events if (dto := wire.dto_of(event)) is not None]

    return [run_step, arbitrate, announce, publish, poll]


def _pull_request_activities(pulls: PullRequests) -> Sequence[Callable[..., Any]]:
    """The activities that show the work on its pull request: stage, draft state, progress, open points, closing."""

    @activity.defn(name=STAGE)
    async def set_stage(stage: wire.StageInput) -> None:
        waiting = Reason(stage.reason) if stage.reason else None
        await pulls.set_stage(wire.context_of(stage.work), stage_of(Phase(stage.phase), waiting))

    @activity.defn(name=READY)
    async def set_ready(ready: wire.ReadyInput) -> None:
        await pulls.set_ready(wire.context_of(ready.work), ready=ready.ready)

    @activity.defn(name=PROGRESS)
    async def progress(update: wire.ProgressInput) -> None:
        position = Position(
            Phase(update.phase),
            Reason(update.reason) if update.reason else None,
            Outcome(update.outcome) if update.outcome else None,
        )
        log = [Entry(Phase(entry.phase), entry.text, entry.at) for entry in update.log]
        phases = wire.course_of(update.work).phases
        body = render_progress(update.work.work_id, phases, log, position, update.updated)
        await pulls.progress(wire.context_of(update.work), body)

    @activity.defn(name=OPEN_POINTS)
    async def note_open_points(note: wire.OpenPointsInput) -> None:
        phase = Phase(note.phase)
        body = open_points_comment(note.work.work_id, ROLES[phase].name, phase.value.replace("_", " "), note.issues)
        await pulls.comment(wire.context_of(note.work), body)

    @activity.defn(name=CLOSE_PULL_REQUEST)
    async def close_pull_request(close: wire.ClosePullRequestInput) -> None:
        await pulls.close(wire.context_of(close.work), close.reason)

    return [set_stage, set_ready, progress, note_open_points, close_pull_request]


def _record_activities(steps: StepRunner) -> Sequence[Callable[..., Any]]:
    """The activity that writes a person's decision into the repository."""

    @activity.defn(name=RECORD_DECISION)
    async def record_decision(record: wire.DecisionRecordInput) -> None:
        await steps.record_decision(
            wire.context_of(record.work),
            DecisionRecord(record.at, record.login, DecisionKind(record.kind), Phase(record.phase), record.note),
        )

    @activity.defn(name=RECORD_ARBITRATION)
    async def record_arbitration(record: wire.ArbitrationRecordInput) -> None:
        await steps.record_arbitration(
            wire.context_of(record.work),
            record.at,
            Phase(record.phase),
            ArbitrationVerdict(record.verdict),
            record.text,
        )

    return [record_decision, record_arbitration]


def build_activities(steps: StepRunner, pulls: PullRequests) -> Sequence[Callable[..., Any]]:
    """Bind the activities to the adapters that carry them out. No globals: the composition root calls this."""
    return [*_steps_activities(steps, pulls), *_pull_request_activities(pulls), *_record_activities(steps)]
