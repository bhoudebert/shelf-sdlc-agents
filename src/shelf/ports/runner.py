"""The engine that runs work durably (Temporal, in production)."""

from collections.abc import Collection, Sequence
from typing import Protocol

from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.work import PersonDecided


class WorkRunner(Protocol):
    """Start work, tell it what a person decided, and look at it."""

    async def start(self, request: WorkRequest) -> WorkId:
        """Begin a piece of work and return its id."""
        ...

    async def decide(self, work_id: WorkId, decision: PersonDecided) -> None:
        """Deliver a person's decision to the work waiting for it."""
        ...

    async def pull_request_closed(self, work_id: WorkId, *, merged: bool) -> None:
        """Tell the work its pull request was merged or closed (what a webhook learns)."""
        ...

    async def view(self, work_id: WorkId) -> WorkView | None:
        """The current picture of one piece of work, or ``None`` when it does not exist."""
        ...

    async def list(self, repos: Collection[RepoRef]) -> Sequence[WorkView]:
        """Every piece of work of these repositories, most recent first."""
        ...
