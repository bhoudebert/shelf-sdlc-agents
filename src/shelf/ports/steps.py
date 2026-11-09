"""What carries out a step (an agent role or the project's checks) and what talks to the pull request."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.ci import Ci
from shelf.domain.model import PullInfo, WorkContext
from shelf.domain.stage import Stage
from shelf.domain.work import AskPerson, Event, RunStep, StepResult


class StepRunner(Protocol):
    """Run one step in a fresh clone and report what came out."""

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        """Run ``step`` for ``work``. A failure that retrying will not fix raises."""
        ...

    async def title(self, work: WorkContext) -> str:
        """The title of the work's pull request by the repository's own convention; never fails, falls back."""
        ...


class PullRequests(Protocol):
    """The pull request that carries the work: where it is published, announced on and watched."""

    async def publish(self, work: WorkContext, title: str) -> str:
        """Open the pull request with ``title`` (or retitle the one that exists) and return its URL."""
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

    async def head(self, work: WorkContext) -> PullInfo:
        """The pull request of this work as it is now: its branch, where the branch is, whether it is open."""
        ...

    async def ci(self, work: WorkContext) -> Ci:
        """What the repository's own CI says about the head of the pull request (``none`` while there is no run)."""
        ...

    async def poll(self, work: WorkContext) -> Sequence[Event]:
        """The events (decisions in comments, a merge or a close) that happened since the last look."""
        ...
