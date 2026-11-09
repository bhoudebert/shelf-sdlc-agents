import asyncio
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from temporalio.client import WorkflowHandle
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.activities import build_activities
from shelf.adapters.temporal.workflow import WorkItemWorkflow
from shelf.domain.ci import Ci, CiState
from shelf.domain.model import PullInfo, WorkContext
from shelf.domain.pipeline import KIND, Kind, Phase
from shelf.domain.policy import CURRENT_PROTOCOL
from shelf.domain.stage import Stage
from shelf.domain.work import (
    AskPerson,
    DecisionKind,
    Event,
    Produced,
    PullRequestClosed,
    Reviewed,
    RunStep,
    StepResult,
    Verdict,
    Verified,
)

QUEUE = "test-queue"
FAST = {"poll_base_seconds": 3600.0, "poll_ceiling_seconds": 3600.0}


def approving(phase: Phase) -> StepResult:
    match KIND[phase]:
        case Kind.REVIEW:
            return Reviewed(Verdict.APPROVE)
        case Kind.VERIFY:
            return Verified(passed=True)
        case _:
            return Produced()


@dataclass
class FakeSteps:
    """Answers steps from a script, approving anything not scripted."""

    script: dict[tuple[Phase, int], StepResult] = field(default_factory=dict[tuple[Phase, int], StepResult])
    ran: list[RunStep] = field(default_factory=list[RunStep])
    behaviour: Callable[[RunStep], Awaitable[StepResult]] | None = None

    async def title(self, work: WorkContext) -> str:
        return "feat: loyalty points"

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        self.ran.append(step)
        if self.behaviour is not None:
            return await self.behaviour(step)
        return self.script.get((step.phase, step.attempt), approving(step.phase))


@dataclass
class FakePulls:
    found: list[Event] = field(default_factory=list[Event])
    announced: list[AskPerson] = field(default_factory=list[AskPerson])
    published: int = 0
    commented: list[str] = field(default_factory=list[str])
    ready: list[bool] = field(default_factory=list[bool])
    stages: list[str] = field(default_factory=list[str])
    titles: list[str] = field(default_factory=list[str])
    progressed: list[str] = field(default_factory=list[str])
    cis: list[Ci] = field(default_factory=list[Ci])
    """What the CI says on each look, in turn; the last one repeats. Nothing scripted means no CI."""
    looked: int = 0
    pull: PullInfo = field(default_factory=lambda: PullInfo("feat/x", "abc", open=True, same_repository=True))

    async def head(self, work: WorkContext) -> PullInfo:
        return self.pull

    async def ci(self, work: WorkContext) -> Ci:
        self.looked += 1
        if not self.cis:
            return Ci(CiState.NONE)
        return self.cis[min(self.looked, len(self.cis)) - 1]

    async def publish(self, work: WorkContext, title: str) -> str:
        self.published += 1
        self.titles.append(title)
        return "https://github.com/acme/shop/pull/1"

    async def progress(self, work: WorkContext, body: str) -> None:
        self.progressed.append(body)

    async def set_ready(self, work: WorkContext, *, ready: bool) -> None:
        self.ready.append(ready)

    async def set_stage(self, work: WorkContext, stage: Stage) -> None:
        self.stages.append(stage.name)

    async def announce(self, work: WorkContext, ask: AskPerson) -> None:
        self.announced.append(ask)

    async def comment(self, work: WorkContext, body: str) -> None:
        self.commented.append(body)

    async def poll(self, work: WorkContext) -> Sequence[Event]:
        found, self.found = self.found, []
        return found


def work_input(entry: str, **overrides: object) -> wire.WorkInput:
    base: dict[str, object] = {
        "work_id": f"work-{uuid.uuid4()}",
        "repo": "acme/shop",
        "requester": "alice",
        "entry": entry,
        "text": "loyalty points",
        "pull_request": 7 if entry in ("pull_request_review", "pull_request_work") else None,
        "protocol": CURRENT_PROTOCOL,
        **FAST,
    }
    return wire.WorkInput(**{**base, **overrides})  # type: ignore[arg-type]


async def until(
    handle: WorkflowHandle[WorkItemWorkflow, str], condition: Callable[[wire.Snapshot], bool]
) -> wire.Snapshot:
    """Wait, with a deadline, until the workflow's snapshot satisfies ``condition``."""
    async with asyncio.timeout(20):
        while True:
            snapshot = await handle.query(WorkItemWorkflow.snapshot)
            if condition(snapshot):
                return snapshot
            await asyncio.sleep(0.05)


def worker(env: WorkflowEnvironment, steps: FakeSteps, pulls: FakePulls) -> Worker:
    return Worker(
        env.client,
        task_queue=QUEUE,
        workflows=[WorkItemWorkflow],
        activities=build_activities(steps, pulls),
    )


async def start(env: WorkflowEnvironment, work: wire.WorkInput) -> WorkflowHandle[WorkItemWorkflow, str]:
    return await env.client.start_workflow(WorkItemWorkflow.run, work, id=work.work_id, task_queue=QUEUE)


async def test_a_pull_request_review_ends_when_the_pull_request_is_merged(env: WorkflowEnvironment) -> None:
    steps, pulls = FakeSteps(), FakePulls()
    async with worker(env, steps, pulls):
        handle = await start(env, work_input("pull_request_review"))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        assert await handle.result() == "merged"
    assert [s.phase for s in steps.ran] == [Phase.CODE_REVIEW]
    assert pulls.published == 0
    assert [a.phase for a in pulls.announced] == [Phase.PULL_REQUEST]


async def test_work_from_a_need_publishes_a_pull_request_and_stops_at_the_spec_gate(env: WorkflowEnvironment) -> None:
    steps, pulls = FakeSteps(), FakePulls()
    async with worker(env, steps, pulls):
        handle = await start(env, work_input("need"))
        waiting = await until(handle, lambda s: s.waiting_for == "gate")
        assert waiting.phase == Phase.SPEC_APPROVAL
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("carol", DecisionKind.APPROVE, ""))
        waiting = await until(handle, lambda s: s.waiting_for == "merge" and bool(s.pull_request_url))
        assert waiting.pull_request_url.endswith("/pull/1")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        assert await handle.result() == "merged"
    assert [s.phase for s in steps.ran] == [
        Phase.INTAKE,
        Phase.SPEC_REVIEW,
        Phase.DESIGN,
        Phase.DESIGN_REVIEW,
        Phase.PLAN,
        Phase.IMPLEMENT,
        Phase.VERIFY,
        Phase.CODE_REVIEW,
    ]
    assert pulls.published >= 1  # opened after the first step, asked for again at the merge
    assert pulls.ready == [True]
    assert "shelf: writing the spec" in pulls.stages
    assert pulls.stages[-1] == "shelf: ready to merge"
    assert pulls.progressed, "the progress comment is updated as the work moves"
    assert any("Now:** ✅ ready to review and merge" in body for body in pulls.progressed)
    assert "Now:** ✅ merged" in pulls.progressed[-1]
    assert "approved" in pulls.progressed[-1]
    assert "UTC</sub>" in pulls.progressed[-1], "every step says when it happened"
    assert "Last action: " in pulls.progressed[-1]


async def test_a_reviewer_asking_for_changes_sends_the_work_back_with_the_issues(env: WorkflowEnvironment) -> None:
    steps = FakeSteps({(Phase.CODE_REVIEW, 0): Reviewed(Verdict.CHANGES, "rename it")})
    pulls = FakePulls()
    async with worker(env, steps, pulls):
        handle = await start(env, work_input("implement"))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        await handle.result()
    redone = [s for s in steps.ran if s.phase is Phase.IMPLEMENT]
    assert [(s.attempt, s.feedback) for s in redone] == [(0, ""), (1, "rename it")]


async def test_a_step_that_fails_asks_a_person_who_resumes_it(env: WorkflowEnvironment) -> None:
    calls = 0

    async def flaky(step: RunStep) -> StepResult:
        nonlocal calls
        message = "model unavailable"
        calls += 1
        if step.phase is Phase.CODE_REVIEW and calls <= 1:
            raise ApplicationError(message, non_retryable=True)
        return approving(step.phase)

    steps = FakeSteps(behaviour=flaky)
    async with worker(env, steps, FakePulls()):
        handle = await start(env, work_input("pull_request_review"))
        failed = await until(handle, lambda s: s.waiting_for == "failure")
        assert "model unavailable" in failed.detail
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("bob", DecisionKind.RESUME, "again"))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, False)
        assert await handle.result() == "closed"


async def test_aborting_cancels_the_running_step(env: WorkflowEnvironment) -> None:
    started = asyncio.Event()

    async def forever(step: RunStep) -> StepResult:
        started.set()
        await asyncio.sleep(60)
        return approving(step.phase)

    steps = FakeSteps(behaviour=forever)
    async with worker(env, steps, FakePulls()):
        handle = await start(env, work_input("pull_request_review"))
        await asyncio.wait_for(started.wait(), 20)
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("bob", DecisionKind.ABORT, ""))
        assert await handle.result() == "aborted"


async def test_the_poller_wakes_a_waiting_work_item_when_the_pull_request_is_merged(env: WorkflowEnvironment) -> None:
    pulls = FakePulls()
    async with worker(env, FakeSteps(), pulls):
        handle = await start(env, work_input("pull_request_review", poll_base_seconds=0.1, poll_ceiling_seconds=0.2))
        await until(handle, lambda s: s.waiting_for == "merge")
        pulls.found = [PullRequestClosed(merged=True)]
        assert await handle.result() == "merged"


async def test_a_finished_history_replays_deterministically(env: WorkflowEnvironment) -> None:
    async with worker(env, FakeSteps(), FakePulls()):
        handle = await start(env, work_input("need"))
        await until(handle, lambda s: s.waiting_for == "gate")
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("carol", DecisionKind.APPROVE, ""))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        await handle.result()
        history = await handle.fetch_history()
    await Replayer(workflows=[WorkItemWorkflow]).replay_workflow(history)


async def test_work_started_by_an_older_release_does_none_of_the_newer_extras(env: WorkflowEnvironment) -> None:
    pulls = FakePulls()
    async with worker(env, FakeSteps(), pulls):
        handle = await start(env, work_input("need", protocol=1))
        await until(handle, lambda s: s.waiting_for == "gate")
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("carol", DecisionKind.APPROVE, ""))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        assert await handle.result() == "merged"
    assert pulls.stages == []
    assert pulls.ready == []
    assert pulls.progressed == []
    assert pulls.published == 1  # opened at the merge, as it always was


async def test_work_on_a_pull_request_never_opens_one_and_readies_the_one_it_has(env: WorkflowEnvironment) -> None:
    steps, pulls = FakeSteps(), FakePulls()
    async with worker(env, steps, pulls):
        handle = await start(env, work_input("pull_request_work"))
        await until(handle, lambda s: s.waiting_for == "merge")
        await handle.signal(WorkItemWorkflow.pull_request_closed, True)
        assert await handle.result() == "merged"
    assert [s.phase for s in steps.ran] == [Phase.IMPLEMENT, Phase.VERIFY, Phase.CODE_REVIEW]
    assert pulls.published == 0, "the pull request already exists: nothing is opened or retitled"
    assert pulls.ready == [True]
