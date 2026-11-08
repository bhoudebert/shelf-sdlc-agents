"""What carries out a step (an agent role or the project's checks) and what talks to the pull request."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.model import WorkContext
from shelf.domain.stage import Stage
from shelf.domain.work import AskPerson, Event, RunStep, StepResult


class StepRunner(Protocol):
    """Run one step in a fresh clone and report what came out."""

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        """Run ``step`` for ``work``. A failure that retrying will not fix raises."""
        ...


class PullRequests(Protocol):
    """The pull request that carries the work: where it is published, announced on and watched."""

    async def publish(self, work: WorkContext) -> str:
        """Open the pull request and return its URL."""
        ...

    async def announce(self, work: WorkContext, ask: AskPerson) -> None:
        """Tell the people on the pull request what the work waits for."""
        ...

    async def progress(self, work: WorkContext, body: str) -> None:
        """Create or update, in place, the one progress comment of this work on the pull request."""
        ...

    async def set_ready(self, work: WorkContext, *, ready: bool) -> None:
        """Mark the pull request ready for review, or back to draft."""
        ...

    async def set_stage(self, work: WorkContext, stage: Stage) -> None:
        """Make ``stage`` the pull request's one ``shelf:`` label, replacing the previous one."""
        ...

    async def comment(self, work: WorkContext, body: str) -> None:
        """Post ``body`` on the pull request (a review, for work that reviews an existing pull request)."""
        ...

    async def poll(self, work: WorkContext) -> Sequence[Event]:
        """The events (decisions in comments, a merge or a close) that happened since the last look."""
        ...
