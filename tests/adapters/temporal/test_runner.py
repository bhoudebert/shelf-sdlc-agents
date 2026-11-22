import asyncio
import itertools
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import SimpleNamespace
from typing import Any

import pytest
from temporalio.client import WorkflowExecutionStatus, WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from shelf.adapters.temporal.runner import TemporalRunner
from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Autonomy, Policy
from shelf.domain.polling import Mode
from shelf.domain.work import DecisionKind, Outcome, PersonDecided, Reason, Reviewed, Verdict
from shelf.ports.runner import UnreachableWorkError
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
        assert board.title == "loyalty points"
        assert board.updated_at, "the board knows when the work last did anything"
        assert dict(board.times)["spec_approval"] == board.updated_at

        await runner.decide(work_id, PersonDecided("carol", DecisionKind.ABORT))
        finished = await _until_finished(runner, work_id)
        assert finished.outcome is Outcome.ABORTED
        assert [v.id for v in await runner.list([REPO])] == [work_id]
        assert await runner.list([RepoRef("other", "repo")]) == []
        assert [v.id for v in await runner.list(None)] == [work_id]


async def test_the_runner_starts_work_with_the_policy_of_the_repository(env: WorkflowEnvironment) -> None:
    configs = FakeConfigs({REPO: RepoConfig(policy=Policy(spec_approval=False))})
    runner = runner_for(env, configs)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        board = await _until(runner, work_id, lambda v: v.waiting_for is Reason.MERGE and bool(v.pull_request_url))
    assert board.pull_request_url.endswith("/pull/1")


async def test_a_review_links_the_pull_request_it_started_from(env: WorkflowEnvironment) -> None:
    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        request = WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, pull_request=7)
        work_id = await runner.start(request)
        view = await _until(runner, work_id, lambda v: v.waiting_for is not None)
    assert view.pull_request_url == f"https://github.com/{REPO.full_name}/pull/7"


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


async def test_many_callers_share_one_set_of_temporal_lookups_for_a_moment(env: WorkflowEnvironment) -> None:
    from unittest.mock import patch  # noqa: PLC0415

    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _until_waiting(runner, work_id, Reason.GATE)
        with patch.object(env.client, "list_workflows", wraps=env.client.list_workflows) as listing:
            first = await runner.list(None)
            second = await runner.list([REPO])
            third = await runner.list([RepoRef("other", "repo")])
        assert listing.call_count == 1
        assert [v.id for v in first] == [v.id for v in second] == [work_id]
        assert third == []


async def test_a_piece_of_work_that_cannot_be_read_is_shown_as_failed_not_hidden(env: WorkflowEnvironment) -> None:
    from unittest.mock import patch  # noqa: PLC0415

    from temporalio.client import WorkflowHandle  # noqa: PLC0415

    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _until_waiting(runner, work_id, Reason.GATE)
        with patch.object(WorkflowHandle, "query", side_effect=RuntimeError("workflow task failing")):
            view = await runner.view(work_id)
    assert view is not None
    assert view.waiting_for is Reason.FAILURE
    assert "cannot be read" in view.detail
    assert (view.repo, view.requester) == (REPO, "alice")


async def test_an_administrator_can_close_work_even_when_it_cannot_be_read(env: WorkflowEnvironment) -> None:
    from unittest.mock import patch  # noqa: PLC0415

    from temporalio.client import WorkflowHandle  # noqa: PLC0415

    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _until_waiting(runner, work_id, Reason.GATE)
        await runner.terminate(work_id, "stuck")
        with patch.object(WorkflowHandle, "query", side_effect=RuntimeError("cannot replay")):
            view = await runner.view(work_id)
    assert view is not None
    assert view.outcome is Outcome.ABORTED
    assert view.waiting_for is None


async def test_closing_work_that_does_not_exist_is_reported_as_unreachable(env: WorkflowEnvironment) -> None:
    with pytest.raises(UnreachableWorkError):
        await runner_for(env).terminate(WorkId("work-nope"), "x")


class FinishedBadly:
    """A workflow handle whose workflow ended with ``status`` and can no longer be queried."""

    id = "work-1"

    def __init__(self, status: WorkflowExecutionStatus, failure: BaseException | None) -> None:
        self.status, self.failure = status, failure

    async def describe(self) -> SimpleNamespace:
        async def memo() -> dict[str, object]:
            return {"repo": "acme/shop", "requester": "alice", "entry": "need", "title": "loyalty points"}

        return SimpleNamespace(status=self.status, memo=memo, close_time=None)

    async def query(self, *args: object) -> None:
        message = "workflow task failed"
        raise RuntimeError(message)

    async def result(self, *, follow_runs: bool) -> None:
        if self.failure is not None:
            raise WorkflowFailureError(cause=self.failure)


def runner_over(handle: FinishedBadly) -> TemporalRunner:
    def get_workflow_handle_for(*_args: object) -> FinishedBadly:
        return handle

    client = SimpleNamespace(get_workflow_handle_for=get_workflow_handle_for)
    return TemporalRunner(client, QUEUE, FakeConfigs(), Mode.SERVER)  # type: ignore[arg-type]


async def test_a_workflow_that_failed_long_ago_is_shown_as_over_with_the_reason_it_gave() -> None:
    handle = FinishedBadly(WorkflowExecutionStatus.FAILED, ApplicationError("list index out of range"))
    view = await runner_over(handle).view(WorkId("work-1"))
    assert view is not None
    assert view.outcome is Outcome.ABORTED
    assert view.waiting_for is None
    assert "its workflow failed" in view.detail
    assert "It said: list index out of range." in view.detail
    assert "start the work again" in view.detail
    assert view.title == "loyalty points"


async def test_a_workflow_that_timed_out_says_so() -> None:
    view = await runner_over(FinishedBadly(WorkflowExecutionStatus.TIMED_OUT, None)).view(WorkId("work-1"))
    assert view is not None
    assert "its workflow timed out" in view.detail
    assert "It said" not in view.detail


async def test_a_running_workflow_that_cannot_be_read_is_still_flagged_for_a_person() -> None:
    view = await runner_over(FinishedBadly(WorkflowExecutionStatus.RUNNING, None)).view(WorkId("work-1"))
    assert view is not None
    assert view.waiting_for is Reason.FAILURE
    assert "cannot be read right now" in view.detail


async def test_the_other_repositories_a_work_reads_are_kept_and_shown_on_the_board(env: WorkflowEnvironment) -> None:
    runner = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        request = WorkRequest(REPO, "alice", EntryPoint.NEED, "ci like foo/bar", context=("foo/bar@v1",))
        work_id = await runner.start(request)
        board = await _until_waiting(runner, work_id, Reason.GATE)
    assert board.context == ("foo/bar@v1",)


async def test_what_the_person_chose_at_the_start_beats_the_repositorys_file(env: WorkflowEnvironment) -> None:
    runner = runner_for(env, FakeConfigs({REPO: RepoConfig(policy=Policy(spec_approval=True, design_review=True))}))
    steps = FakeSteps({(Phase.SPEC_REVIEW, 0): Reviewed(Verdict.ESCALATE, "cannot decide")})
    chosen = Autonomy(spec_approval=False, design_review=False, proceed_on_deadlock=True)
    async with worker(env, steps, FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x", autonomy=chosen))
        await _until(runner, work_id, lambda v: v.waiting_for is Reason.MERGE)
    assert Phase.DESIGN_REVIEW not in {step.phase for step in steps.ran}
    assert Phase.PLAN in {step.phase for step in steps.ran}


async def test_the_board_says_which_stops_a_run_does_without(env: WorkflowEnvironment) -> None:
    runner = runner_for(env, FakeConfigs({REPO: RepoConfig(policy=Policy())}))
    chosen = Autonomy(spec_approval=False, design_review=True, proceed_on_deadlock=True)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x", autonomy=chosen))
        board = await _until(runner, work_id, lambda v: v.waiting_for is not None)
        kept = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "y", autonomy=Autonomy.strictest()))
        plain = await _until(runner, kept, lambda v: v.waiting_for is not None)
    assert board.unattended == ("spec", "deadlock")
    assert plain.unattended == ()


async def test_the_board_says_how_hard_each_review_looks(env: WorkflowEnvironment) -> None:
    from shelf.domain.review import ReviewDepth  # noqa: PLC0415

    runner = runner_for(env, FakeConfigs({REPO: RepoConfig(policy=Policy())}))
    chosen = Autonomy(
        spec_approval=True,
        design_review=True,
        proceed_on_deadlock=False,
        spec_review_depth=ReviewDepth.QUICK,
        design_review_depth=ReviewDepth.THOROUGH,
    )
    off = Autonomy(spec_approval=True, design_review=False, proceed_on_deadlock=False)
    async with worker(env, FakeSteps(), FakePulls()):
        work_id = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x", autonomy=chosen))
        board = await _until(runner, work_id, lambda v: v.waiting_for is not None)
        skipped = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "y", autonomy=off))
        without = await _until(runner, skipped, lambda v: v.waiting_for is not None)
    assert board.review_depths == (("spec", "quick"), ("design", "thorough"))
    assert dict(without.review_depths)["design"] == "off"


class QueryCount:
    """Counts the queries sent to workflows (each one makes the worker replay that workflow's history)."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def patched(self) -> AbstractContextManager[object]:
        from unittest.mock import patch  # noqa: PLC0415

        from temporalio.client import WorkflowHandle  # noqa: PLC0415

        original: Any = WorkflowHandle.query  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        asked = self.asked

        async def counting(handle: Any, *args: Any, **kwargs: Any) -> Any:
            asked.append(handle.id)
            return await original(handle, *args, **kwargs)

        return patch.object(WorkflowHandle, "query", counting)


def fresh_runner(env: WorkflowEnvironment) -> TemporalRunner:
    """A runner that shares nothing between two lists, so every list is a real look."""
    numbers = itertools.count(1)
    return TemporalRunner(
        env.client,
        QUEUE,
        FakeConfigs(),
        Mode.SERVER,
        next_id=lambda: WorkId(f"work-{next(numbers)}"),
        cache_seconds=0.0,
    )


async def _finish(runner: TemporalRunner, work_id: WorkId) -> None:
    await _until_waiting(runner, work_id, Reason.GATE)
    await runner.decide(work_id, PersonDecided("carol", DecisionKind.ABORT))
    await _until_finished(runner, work_id)
    await _until_closed(runner, work_id)


async def _until_closed(runner: TemporalRunner, work_id: WorkId) -> None:
    """Wait until Temporal itself says the workflow is over, in its description and in the list.

    The view says the work is finished a moment before the workflow closes, and the list lags behind the description:
    a test that counts looks must not start in that gap.
    """
    handle = runner.client.get_workflow_handle(work_id)
    async with asyncio.timeout(20):
        while True:
            described = (await handle.describe()).status
            listed = [e.status async for e in runner.client.list_workflows(f'WorkflowId = "{work_id}"')]
            if (
                described != WorkflowExecutionStatus.RUNNING
                and listed
                and WorkflowExecutionStatus.RUNNING not in listed
            ):
                return
            await asyncio.sleep(0.05)


async def test_a_finished_work_is_looked_at_once_and_then_remembered(env: WorkflowEnvironment) -> None:
    starter = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        done = await starter.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _finish(starter, done)
        runner = fresh_runner(env)  # it has seen nothing yet
        count = QueryCount()
        with count.patched():
            first = await runner.list(None)
            after_first = len(count.asked)
            second = await runner.list(None)
            third = await runner.list(None)
    assert after_first == 1
    assert len(count.asked) == 1, "a finished work cannot change: it is not replayed again"
    assert first == second == third
    assert first[0].outcome is Outcome.ABORTED


async def test_a_work_that_is_still_running_is_asked_again_every_time(env: WorkflowEnvironment) -> None:
    runner = fresh_runner(env)
    async with worker(env, FakeSteps(), FakePulls()):
        running = await runner.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _until_waiting(runner, running, Reason.GATE)
        count = QueryCount()
        with count.patched():
            await runner.list(None)
            await runner.list(None)
            await runner.list(None)
    assert count.asked == [running] * 3


async def test_only_the_running_work_is_asked_when_there_is_finished_work_too(env: WorkflowEnvironment) -> None:
    starter = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        done = await starter.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "old"))
        await _finish(starter, done)
        running = await starter.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "new"))
        await _until_waiting(starter, running, Reason.GATE)
        runner = fresh_runner(env)
        await runner.list(None)  # the finished one is looked at here, once
        count = QueryCount()
        with count.patched():
            await runner.list(None)
            await runner.list(None)
    assert count.asked == [running, running]


async def test_the_page_of_one_finished_work_does_not_replay_it_on_every_refresh(env: WorkflowEnvironment) -> None:
    starter = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        done = await starter.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _finish(starter, done)
        runner = fresh_runner(env)
        count = QueryCount()
        with count.patched():
            first = await runner.view(done)
            again = await runner.view(done)
            more = await runner.view(done)
    assert len(count.asked) == 1
    assert first == again == more


async def test_a_look_that_failed_for_now_is_not_remembered_for_a_finished_work(env: WorkflowEnvironment) -> None:
    from unittest.mock import patch  # noqa: PLC0415

    from temporalio.client import WorkflowHandle  # noqa: PLC0415

    starter = runner_for(env)
    async with worker(env, FakeSteps(), FakePulls()):
        done = await starter.start(WorkRequest(REPO, "alice", EntryPoint.NEED, "x"))
        await _finish(starter, done)
        runner = fresh_runner(env)
        with patch.object(WorkflowHandle, "query", side_effect=RuntimeError("the worker is down")):
            broken = await runner.view(done)
        later = await runner.view(done)
    assert broken is not None
    assert broken.waiting_for is Reason.FAILURE
    assert later is not None
    assert later.outcome is Outcome.ABORTED, "the failure of one look is not kept as the picture of a finished work"
