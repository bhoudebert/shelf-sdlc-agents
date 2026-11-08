import asyncio
import itertools
from collections.abc import Callable

from temporalio.testing import WorkflowEnvironment

from shelf.adapters.temporal.runner import TemporalRunner
from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Policy
from shelf.domain.polling import Mode
from shelf.domain.work import DecisionKind, Outcome, PersonDecided, Reason
from tests.adapters.temporal.test_workflow import QUEUE, FakePulls, FakeSteps, worker
from tests.fakes import FakeConfigs

REPO = RepoRef("acme", "shop")


def runner_for(env: WorkflowEnvironment, configs: FakeConfigs | None = None) -> TemporalRunner:
    numbers = itertools.count(1)
    return TemporalRunner(
        env.client, QUEUE, configs or FakeConfigs(), Mode.SERVER, next_id=lambda: WorkId(f"work-{next(numbers)}")
    )


async def test_work_started_through_the_runner_shows_on_the_board_and_takes_decisions(env: WorkflowEnvironment) -> None:
    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "loyalty points"))
        assert work_id == "work-1"
        board = await _until_waiting(runner, work_id, Reason.GATE)
        assert (board.repo, board.requester, board.entry) == (REPO, "alice", EntryPoint.NEED)
        assert board.phase is Phase.SPEC_APPROVAL

        await runner.decide(work_id, PersonDecided("carol", DecisionKind.ABORT))
        finished = await _until_finished(runner, work_id)
        assert finished.outcome is Outcome.ABORTED
        assert [v.id for v in await runner.list([REPO])] == [work_id]
        assert await runner.list([RepoRef("other", "repo")]) == []


async def test_the_runner_starts_work_with_the_policy_of_the_repository(env: WorkflowEnvironment) -> None:
    configs = FakeConfigs({REPO: RepoConfig(policy=Policy(spec_approval=False))})
    runner = runner_for(env, configs)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        board = await _until_waiting(runner, work_id, Reason.MERGE)
    assert board.pull_request_url.endswith("/pull/1")


async def test_an_unknown_piece_of_work_has_no_view(env: WorkflowEnvironment) -> None:
    assert await runner_for(env).view(WorkId("nope")) is None


async def _until(runner: TemporalRunner, work_id: WorkId, condition: Callable[[WorkView], bool]) -> WorkView:
    async with asyncio.timeout(20):
        while True:
            view = await runner.view(work_id)
            if view is not None and condition(view):
                return view
            await asyncio.sleep(0.05)


async def _until_waiting(runner: TemporalRunner, work_id: WorkId, reason: Reason) -> WorkView:
    return await _until(runner, work_id, lambda view: view.waiting_for is reason)


async def _until_finished(runner: TemporalRunner, work_id: WorkId) -> WorkView:
    return await _until(runner, work_id, lambda view: view.outcome is not None)
