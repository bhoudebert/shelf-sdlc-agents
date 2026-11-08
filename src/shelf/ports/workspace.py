"""A fresh clone for one step, and what a step may do with it."""

from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shelf.domain.model import RepoRef


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome of one command run in the clone."""

    command: str
    exit_code: int
    output: str


@dataclass(frozen=True, slots=True)
class Checkout:
    """What to clone: the work's branch cut from ``base`` (or the head of a pull request, read-only)."""

    repo: RepoRef
    token: str
    branch: str
    base: str
    pull_request: int | None = None


class Workspace(Protocol):
    """One clone, alive for one step."""

    @property
    def path(self) -> Path:
        """The working directory."""
        ...

    async def run(self, command: str) -> CheckResult:
        """Run a shell command in the clone, capturing its output."""
        ...

    async def commit_and_push(self, message: str) -> bool:
        """Commit everything changed and push the branch. Returns whether there was anything to commit."""
        ...


class Workspaces(Protocol):
    """Opens clones, and removes them when the step ends."""

    def open(self, checkout: Checkout) -> AbstractAsyncContextManager[Workspace]:
        """A fresh clone for ``checkout``."""
        ...
