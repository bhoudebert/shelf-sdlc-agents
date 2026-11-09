"""The ``WorkRunner`` port over a Temporal client: one workflow per piece of work."""

import asyncio
import time
import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field

from temporalio.client import Client, WorkflowExecutionStatus, WorkflowHandle
from temporalio.service import RPCError

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.workflow import WorkItemWorkflow
from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import CURRENT_PROTOCOL
from shelf.domain.polling import Mode, poll_bounds
from shelf.domain.titles import summary
from shelf.domain.work import Outcome, PersonDecided, Reason
from shelf.ports.configs import RepoConfigs
from shelf.ports.runner import UnreachableWorkError

WORKFLOW_TYPE = "WorkItem"
MAX_CONCURRENT_LOOKS = 8


def new_work_id() -> WorkId:
    """A fresh id for a piece of work."""
    return WorkId(f"work-{uuid.uuid4().hex[:12]}")


TERMINATED = "This work was closed by an administrator because it could not be steered any more."


@dataclass(frozen=True, slots=True)
class TemporalRunner:
    """Starts, signals and inspects ``WorkItem`` workflows."""

    client: Client
    task_queue: str
    configs: RepoConfigs
    mode: Mode = Mode.LOCAL
    web_url: str = "https://github.com"
    """Where pull requests are shown, to link the one a review started from."""
    next_id: Callable[[], WorkId] = field(default=new_work_id)
    cache_seconds: float = 2.0
    """How long a list of all work is shared between callers: many open boards cost one set of Temporal calls."""
    clock: Callable[[], float] = time.monotonic
    _listed: dict[str, tuple[float, Sequence[WorkView]]] = field(
        default_factory=dict[str, tuple[float, Sequence[WorkView]]], repr=False
    )

    async def start(self, request: WorkRequest) -> WorkId:
        """Start a workflow for ``request`` with the policy of its repository."""
        config = await self.configs.load(request.repo)
        base, ceiling = poll_bounds(self.mode)
        work_id = self.next_id()
        work = wire.WorkInput(
            work_id=work_id,
            repo=request.repo.full_name,
            requester=request.requester,
            entry=request.entry,
            text=request.text,
            pull_request=request.pull_request,
            max_rounds=config.policy.max_rounds,
            spec_approval=config.policy.spec_approval,
            design_review=config.policy.design_review,
            poll_base_seconds=base.total_seconds(),
            poll_ceiling_seconds=ceiling.total_seconds(),
            protocol=CURRENT_PROTOCOL,
        )
        await self.client.start_workflow(
            WorkItemWorkflow.run,
            work,
            id=work_id,
            task_queue=self.task_queue,
            memo={
                "repo": work.repo,
                "requester": work.requester,
                "entry": work.entry,
                "title": summary(work.text),
                **({"pull_request": work.pull_request} if work.pull_request is not None else {}),
            },
        )
        return work_id

    async def decide(self, work_id: WorkId, decision: PersonDecided) -> None:
        """Signal the workflow with a person's decision."""
        handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, work_id)
        try:
            await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto(decision.by, decision.kind, decision.note))
        except RPCError as error:
            raise UnreachableWorkError(work_id) from error

    async def terminate(self, work_id: WorkId, reason: str) -> None:
        """End the workflow without running its code: the way to close one an older release left behind."""
        handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, work_id)
        try:
            await handle.terminate(reason)
        except RPCError as error:
            raise UnreachableWorkError(work_id) from error

    async def pull_request_closed(self, work_id: WorkId, *, merged: bool) -> None:
        """Signal the workflow that its pull request was merged or closed."""
        handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, work_id)
        await handle.signal(WorkItemWorkflow.pull_request_closed, merged)

    async def view(self, work_id: WorkId) -> WorkView | None:
        """The current picture of one piece of work."""
        handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, work_id)
        return await self._view(handle)

    async def list(self, repos: Collection[RepoRef] | None) -> Sequence[WorkView]:
        """Every piece of work on ``repos`` (on every repository when ``None``), most recent first."""
        everything = await self._everything()
        if repos is None:
            return everything
        wanted = {repo.full_name for repo in repos}
        return [view for view in everything if view.repo.full_name in wanted]

    async def _everything(self) -> Sequence[WorkView]:
        """All work, looked at concurrently and shared for a moment between callers."""
        cached = self._listed.get("all")
        if cached is not None and self.clock() - cached[0] < self.cache_seconds:
            return cached[1]
        gate = asyncio.Semaphore(MAX_CONCURRENT_LOOKS)

        async def look(workflow_id: str) -> WorkView | None:
            async with gate:
                return await self._view(self.client.get_workflow_handle_for(WorkItemWorkflow.run, workflow_id))

        ids = [execution.id async for execution in self.client.list_workflows(f'WorkflowType = "{WORKFLOW_TYPE}"')]
        looked = await asyncio.gather(*(look(workflow_id) for workflow_id in ids))
        views: Sequence[WorkView] = tuple(view for view in looked if view is not None)
        self._listed["all"] = (self.clock(), views)
        return views

    async def _view(self, handle: WorkflowHandle[WorkItemWorkflow, str]) -> WorkView | None:
        """The picture of one piece of work. One that exists but cannot be read is shown as failed, never hidden."""
        try:
            description = await handle.describe()
            memo = await description.memo()
            repo, requester, entry = (
                RepoRef.parse(str(memo["repo"])),
                str(memo["requester"]),
                EntryPoint(str(memo["entry"])),
            )
        except Exception:  # noqa: BLE001 - not a piece of work of ours, or not there at all
            return None
        try:
            snapshot = await handle.query(WorkItemWorkflow.snapshot)
        except Exception as error:  # noqa: BLE001 - it exists, but its workflow task fails (an older release, or closed)
            if description.status == WorkflowExecutionStatus.TERMINATED:  # closed by an administrator
                return WorkView(
                    WorkId(handle.id),
                    repo,
                    requester,
                    entry,
                    Phase.INTAKE,
                    detail=TERMINATED,
                    outcome=Outcome.ABORTED,
                    title=str(memo.get("title") or ""),
                )
            kind = type(error).__name__
            message = f"This work cannot be read right now ({kind}). It may have been started by an older release."
            return WorkView(
                WorkId(handle.id),
                repo,
                requester,
                entry,
                Phase.INTAKE,
                waiting_for=Reason.FAILURE,
                detail=message,
                title=str(memo.get("title") or ""),
            )
        return WorkView(
            id=WorkId(handle.id),
            repo=repo,
            requester=requester,
            entry=entry,
            phase=Phase(snapshot.phase),
            waiting_for=Reason(snapshot.waiting_for) if snapshot.waiting_for else None,
            detail=snapshot.detail,
            outcome=Outcome(snapshot.outcome) if snapshot.outcome else None,
            pull_request_url=snapshot.pull_request_url or self._link_of(repo, memo.get("pull_request")),
            title=str(memo.get("title") or ""),
        )

    def _link_of(self, repo: RepoRef, number: object) -> str:
        """The link to the pull request a review started from; nothing for work that opens its own."""
        return f"{self.web_url.rstrip('/')}/{repo.full_name}/pull/{number}" if isinstance(number, int) else ""
