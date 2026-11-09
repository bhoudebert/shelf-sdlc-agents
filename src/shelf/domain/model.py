"""The nouns of the factory: who, which repository, what was asked, what can be shown."""

from dataclasses import dataclass
from typing import NewType

from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.work import Outcome, Reason

WorkId = NewType("WorkId", str)


@dataclass(frozen=True, slots=True)
class RepoRef:
    """A GitHub repository."""

    owner: str
    name: str

    @property
    def full_name(self) -> str:
        """The ``owner/name`` form."""
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, full_name: str) -> "RepoRef":
        """Read ``owner/name``; raise ``ValueError`` on anything else."""
        owner, separator, name = full_name.partition("/")
        if not (owner and separator and name) or "/" in name:
            message = f"not a repository name: {full_name!r}"
            raise ValueError(message)
        return cls(owner, name)


@dataclass(frozen=True, slots=True)
class Identity:
    """A signed-in person, as GitHub knows them."""

    login: str
    organisations: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class WorkRequest:
    """What a person asks for when they start work from the UI."""

    repo: RepoRef
    requester: str
    entry: EntryPoint
    text: str = ""
    """The need, or the provided document, depending on the entry point."""
    pull_request: int | None = None
    """The pull request to review, for that entry point."""
    context: tuple[str, ...] = ()
    """Other repositories the agents may read as reference, each as ``owner/name@ref:folder`` (see ``ContextRepo``)."""


@dataclass(frozen=True, slots=True)
class WorkView:
    """What the board shows about a piece of work."""

    id: WorkId
    repo: RepoRef
    requester: str
    entry: EntryPoint
    phase: Phase
    waiting_for: Reason | None = None
    detail: str = ""
    outcome: Outcome | None = None
    pull_request_url: str = ""
    title: str = ""
    context: tuple[str, ...] = ()
    """The other repositories this work reads as reference, each as ``owner/name@ref:folder``."""
    updated_at: str = ""
    """When the work last did anything (ISO, UTC); empty for work started before times were kept."""
    times: tuple[tuple[str, str], ...] = ()
    """For each phase (by name), when something last happened there."""
    """A line of the request, to tell this work from another on the board; empty for work started before it was kept."""


@dataclass(frozen=True, slots=True)
class PullInfo:
    """What GitHub says a pull request is, as far as starting and doing work on it needs."""

    branch: str
    """The branch it was opened from."""
    sha: str
    """Where that branch is now."""
    open: bool
    same_repository: bool
    """False for a pull request from a fork, whose branch the App cannot push to."""


@dataclass(frozen=True, slots=True)
class WorkContext:
    """Everything a step needs to know about the piece of work it serves."""

    id: WorkId
    request: WorkRequest
