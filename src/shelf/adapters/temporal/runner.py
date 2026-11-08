"""The ``WorkRunner`` port over a Temporal client: one workflow per piece of work."""

import uuid
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field

from temporalio.client import Client, WorkflowHandle

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.workflow import WorkItemWorkflow
from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.polling import Mode, poll_bounds
from shelf.domain.work import Outcome, PersonDecided, Reason
from shelf.ports.configs import RepoConfigs

WORKFLOW_TYPE = "WorkItem"


def new_work_id() -> WorkId:
    """A fresh id for a piece of work."""
    return WorkId(f"work-{uuid.uuid4().hex[:12]}")


@dataclass(frozen=True, slots=True)
class TemporalRunner:
    """Starts, signals and inspects ``WorkItem`` workflows."""

    client: Client
    task_queue: str
    configs: RepoConfigs
    mode: Mode = Mode.LOCAL
    next_id: Callable[[], WorkId] = field(default=new_work_id)

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
        )
        await self.client.start_workflow(
            WorkItemWorkflow.run,
            work,
            id=work_id,
            task_queue=self.task_queue,
            memo={"repo": work.repo, "requester": work.requester, "entry": work.entry},
        )
        return work_id

    async def decide(self, work_id: WorkId, decision: PersonDecided) -> None:
        """Signal the workflow with a person's decision."""
        handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, work_id)
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto(decision.by, decision.kind, decision.note))

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
        wanted = None if repos is None else {repo.full_name for repo in repos}
        views: list[WorkView] = []
        async for execution in self.client.list_workflows(f'WorkflowType = "{WORKFLOW_TYPE}"'):
            handle = self.client.get_workflow_handle_for(WorkItemWorkflow.run, execution.id)
            view = await self._view(handle)
            if view is not None and (wanted is None or view.repo.full_name in wanted):
                views.append(view)
        return views

    async def _view(self, handle: WorkflowHandle[WorkItemWorkflow, str]) -> WorkView | None:
        try:
            description = await handle.describe()
            memo = await description.memo()
            snapshot = await handle.query(WorkItemWorkflow.snapshot)
        except Exception:  # noqa: BLE001 - an unknown or unreadable workflow is simply not on the board
            return None
        return WorkView(
            id=WorkId(handle.id),
            repo=RepoRef.parse(str(memo["repo"])),
            requester=str(memo["requester"]),
            entry=EntryPoint(str(memo["entry"])),
            phase=Phase(snapshot.phase),
            waiting_for=Reason(snapshot.waiting_for) if snapshot.waiting_for else None,
            detail=snapshot.detail,
            outcome=Outcome(snapshot.outcome) if snapshot.outcome else None,
            pull_request_url=snapshot.pull_request_url,
        )
