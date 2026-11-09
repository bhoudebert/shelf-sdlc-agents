"""The workflow: a thin interpreter of the pure work-item state machine.

Everything that decides lives in ``shelf.domain.work``. This module only feeds it events (the end of a step, a
person's decision, what the poller found on the pull request) and runs the commands it returns. Keep it that way: the
workflow must stay deterministic, and it is, because the function it calls is pure.
"""

import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from shelf.adapters.temporal import wire
    from shelf.domain.pipeline import Phase
    from shelf.domain.polling import next_interval
    from shelf.domain.progress import describe
    from shelf.domain.work import (
        AskPerson,
        AwaitingPerson,
        CancelStep,
        Command,
        Conclude,
        Event,
        Finished,
        Outcome,
        PersonDecided,
        PublishPullRequest,
        PullRequestClosed,
        Running,
        RunStep,
        SetPullRequestReady,
        State,
        StepDone,
        StepFailed,
        decide,
        start,
    )

RUN_STEP = "shelf_run_step"
ANNOUNCE = "shelf_announce"
PUBLISH = "shelf_publish_pull_request"
POLL = "shelf_poll_pull_request"
STAGE = "shelf_set_stage"
READY = "shelf_set_ready"
PROGRESS = "shelf_progress"

STEP_TIMEOUT = timedelta(minutes=45)
STEP_HEARTBEAT = timedelta(seconds=60)
GITHUB_TIMEOUT = timedelta(minutes=2)
PUBLISH_TIMEOUT = timedelta(minutes=6)
"""Publishing also names the pull request, which runs a short agent."""


@workflow.defn(name="WorkItem")
class WorkItemWorkflow:
    """One piece of work, from its entry point to a merge, a close or an abort."""

    def __init__(self) -> None:
        """Start with nothing decided, nothing running and an empty inbox."""
        self._events: asyncio.Queue[Event] = asyncio.Queue()
        self._state: State | None = None
        self._phase = Phase.INTAKE
        self._pull_request_url = ""
        self._step: asyncio.Task[None] | None = None
        self._outcome = Outcome.CLOSED
        self._quiet_interval = timedelta(0)
        self._log: list[wire.LogEntryDto] = []
        self._updated_at = ""
        self._times: dict[str, str] = {}

    @workflow.signal
    def decided(self, decision: wire.DecisionDto) -> None:
        """A person decided."""
        self._events.put_nowait(wire.decision_of(decision))

    @workflow.signal
    def pull_request_closed(self, merged: bool) -> None:  # noqa: FBT001 - signal arguments are positional
        """GitHub told us the pull request was merged or closed."""
        self._events.put_nowait(PullRequestClosed(merged=merged))

    @workflow.query
    def snapshot(self) -> wire.Snapshot:
        """Where the work is, for the board."""
        if self._state is None:
            return wire.Snapshot(self._phase)
        return wire.snapshot_of(self._state, self._phase, self._pull_request_url, self._updated_at, self._times)

    @workflow.run
    async def run(self, work: wire.WorkInput) -> str:
        """Run the work until it ends, and return how it ended."""
        course = wire.course_of(work)
        self._quiet_interval = timedelta(seconds=work.poll_base_seconds)
        poller = asyncio.create_task(self._poll(work))
        try:
            self._touch(self._phase)
            self._state, commands = start(course)
            await self._execute(work, commands)
            await self._progress(work)
            while not isinstance(self._state, Finished):
                event = await self._events.get()
                self._quiet_interval = timedelta(seconds=work.poll_base_seconds)
                self._note(self._state, event)
                self._touch(self._phase)
                self._state, commands = decide(course, self._state, event)
                await self._execute(work, commands)
                await self._progress(work)
        finally:
            poller.cancel()
        await workflow.wait_condition(workflow.all_handlers_finished)
        return self._outcome

    async def _execute(self, work: wire.WorkInput, commands: tuple[Command, ...]) -> None:
        for command in commands:
            match command:
                case RunStep(phase):
                    self._phase = phase
                    self._touch(phase)
                    await self._stage(work, phase, "")
                    self._step = asyncio.create_task(self._run_step(work, command))
                case CancelStep():
                    self._cancel_step()
                case AskPerson(phase, reason, detail):
                    self._phase = phase
                    self._touch(phase)
                    await self._stage(work, phase, reason)
                    await self._announce(work, phase, reason, detail)
                case SetPullRequestReady(ready):
                    await self._set_ready(work, ready=ready)
                case PublishPullRequest():
                    await self._publish(work)
                case Conclude(outcome):
                    self._outcome = outcome
                    self._cancel_step()

    @staticmethod
    def _now() -> str:
        return workflow.now().isoformat(timespec="seconds")

    def _touch(self, phase: Phase) -> None:
        """Remember when the work last did something, and when it last did something at ``phase``.

        ``workflow.now()`` replays the same on every replay, and nothing here orders a command, so histories recorded
        before times were kept replay unchanged.
        """
        now = self._now()
        self._updated_at = now
        self._times[phase] = now

    def _note(self, state: State, event: Event) -> None:
        """Remember, for the progress comment, what the event meant at the phase the work was in."""
        match state, event:
            case Running(phase, attempt), StepDone(result):
                self._log.append(wire.LogEntryDto(phase, describe(result, attempt), self._now()))
            case Running(phase), StepFailed(reason):
                self._log.append(wire.LogEntryDto(phase, f"failed: {reason[:80]}", self._now()))
            case AwaitingPerson(phase), PersonDecided(_, kind):
                self._log.append(wire.LogEntryDto(phase, f"you: {kind}", self._now()))
            case _:
                pass

    async def _progress(self, work: wire.WorkInput) -> None:
        """Update the progress comment. Cosmetic: a failure never stops the work."""
        state = self._state
        if state is None or not wire.course_of(work).opens_early:
            return
        waiting = state.reason if isinstance(state, AwaitingPerson) else None
        outcome = state.outcome if isinstance(state, Finished) else None
        try:
            await workflow.execute_activity(
                PROGRESS,
                wire.ProgressInput(work, list(self._log), self._phase, waiting or "", outcome or "", self._updated_at),
                start_to_close_timeout=GITHUB_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError:
            workflow.logger.warning("could not update the progress comment")

    async def _stage(self, work: wire.WorkInput, phase: Phase, reason: str) -> None:
        """Show on the pull request what is happening. Cosmetic: a failure never stops the work."""
        if not wire.course_of(work).opens_early:  # work started before this existed keeps its original behaviour
            return
        try:
            await workflow.execute_activity(
                STAGE,
                wire.StageInput(work, phase, reason),
                start_to_close_timeout=GITHUB_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
        except ActivityError:
            workflow.logger.warning("could not set the stage label at %s", phase)

    async def _set_ready(self, work: wire.WorkInput, *, ready: bool) -> None:
        """Mark the pull request ready for review, or back to draft."""
        if not wire.course_of(work).opens_early:
            return
        try:
            await workflow.execute_activity(
                READY,
                wire.ReadyInput(work, ready),
                start_to_close_timeout=GITHUB_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except ActivityError:
            workflow.logger.warning("could not change the draft state of the pull request")

    async def _publish(self, work: wire.WorkInput) -> None:
        """Open the pull request (or find it). Failing to is logged, not fatal: the merge phase asks again."""
        try:
            self._pull_request_url = await workflow.execute_activity(
                PUBLISH,
                work,
                result_type=str,
                start_to_close_timeout=PUBLISH_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
        except ActivityError:
            workflow.logger.warning("could not open the pull request yet")

    def _cancel_step(self) -> None:
        if self._step is not None and not self._step.done():
            self._step.cancel()
        self._step = None

    async def _run_step(self, work: wire.WorkInput, command: RunStep) -> None:
        try:
            output = await workflow.execute_activity(
                RUN_STEP,
                wire.StepInput(work, command.phase, command.attempt, command.feedback),
                result_type=wire.StepOutput,
                start_to_close_timeout=STEP_TIMEOUT,
                heartbeat_timeout=STEP_HEARTBEAT,
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            event: Event = StepDone(wire.result_of(output))
        except ActivityError as error:
            event = StepFailed(str(error.cause or error))
        self._events.put_nowait(event)

    async def _announce(self, work: wire.WorkInput, phase: Phase, reason: str, detail: str) -> None:
        try:
            await workflow.execute_activity(
                ANNOUNCE,
                wire.AskInput(work, phase, reason, detail),
                start_to_close_timeout=GITHUB_TIMEOUT,
                retry_policy=RetryPolicy(maximum_attempts=5),
            )
        except ActivityError:
            workflow.logger.warning("could not announce the wait at %s", phase)

    async def _poll(self, work: wire.WorkInput) -> None:
        """Look at the pull request on a durable timer that slows down while nothing happens."""
        ceiling = timedelta(seconds=work.poll_ceiling_seconds)
        while True:
            await workflow.sleep(self._quiet_interval)
            if isinstance(self._state, AwaitingPerson):
                found = await workflow.execute_activity(
                    POLL,
                    work,
                    result_type=list[wire.EventDto],
                    start_to_close_timeout=GITHUB_TIMEOUT,
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                for dto in found:
                    if (event := wire.event_of(dto)) is not None:
                        self._events.put_nowait(event)
            self._quiet_interval = next_interval(self._quiet_interval, ceiling)
