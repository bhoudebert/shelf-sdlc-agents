"""The activities: the only place where the workflow touches the world, built from the ports they need."""

from collections.abc import Callable, Sequence
from typing import Any

from temporalio import activity

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.workflow import ANNOUNCE, POLL, PUBLISH, RUN_STEP
from shelf.domain.pipeline import Phase
from shelf.domain.work import AskPerson, Reason, RunStep
from shelf.ports.steps import PullRequests, StepRunner


def build_activities(steps: StepRunner, pulls: PullRequests) -> Sequence[Callable[..., Any]]:
    """Bind the activities to the adapters that carry them out. No globals: the composition root calls this."""

    @activity.defn(name=RUN_STEP)
    async def run_step(step: wire.StepInput) -> wire.StepOutput:
        result = await steps.run(wire.context_of(step.work), RunStep(Phase(step.phase), step.attempt, step.feedback))
        return wire.output_of(result)

    @activity.defn(name=ANNOUNCE)
    async def announce(ask: wire.AskInput) -> None:
        await pulls.announce(wire.context_of(ask.work), AskPerson(Phase(ask.phase), Reason(ask.reason), ask.detail))

    @activity.defn(name=PUBLISH)
    async def publish(work: wire.WorkInput) -> str:
        return await pulls.publish(wire.context_of(work))

    @activity.defn(name=POLL)
    async def poll(work: wire.WorkInput) -> list[wire.EventDto]:
        events = await pulls.poll(wire.context_of(work))
        return [dto for event in events if (dto := wire.dto_of(event)) is not None]

    return [run_step, announce, publish, poll]
