"""The code forge (GitHub) as the application needs it on behalf of a signed-in person."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.model import Identity, PullInfo, RepoRef


class Forge(Protocol):
    """What a person's own GitHub token lets the application see."""

    async def exchange_code(self, code: str) -> str:
        """Trade the OAuth ``code`` from the sign-in redirect for the person's token."""
        ...

    async def identity(self, user_token: str) -> Identity:
        """Who the token belongs to, with the organisations they belong to."""
        ...

    async def memberships(self, login: str, organisations: frozenset[str]) -> frozenset[str]:
        """Which of ``organisations`` the person belongs to.

        Asked separately because a GitHub App's own token is never told its holder's organisations.
        """
        ...

    async def pull_request(self, user_token: str, repo: RepoRef, number: int) -> PullInfo | None:
        """The pull request ``number`` of ``repo`` as this person sees it, or ``None`` when they cannot see one."""
        ...

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        """The repositories the app is installed on that this person can also access."""
        ...
