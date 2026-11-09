"""The forge, narrowed to the repositories this instance is meant to serve."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from shelf.domain.access import AccessRules, may_use_repository
from shelf.domain.model import Identity, PullInfo, RepoRef
from shelf.ports.forge import Forge


@dataclass(frozen=True, slots=True)
class ScopedForge:
    """Wraps a ``Forge`` so that a repository of an owner the operator did not list does not exist for the application.

    Anyone who is signed in can install the App on an account or organisation of their own, and the board would then
    list its repositories and let agents work there on the operator's model account. The rules are asked each time, so
    an edit of the access file applies at once.
    """

    inner: Forge
    rules: Callable[[], AccessRules]

    async def exchange_code(self, code: str) -> str:
        """Passed through: the owner of a repository is not in question yet."""
        return await self.inner.exchange_code(code)

    async def identity(self, user_token: str) -> Identity:
        """Passed through."""
        return await self.inner.identity(user_token)

    async def memberships(self, login: str, organisations: frozenset[str]) -> frozenset[str]:
        """Passed through."""
        return await self.inner.memberships(login, organisations)

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        """Only the repositories of a listed organisation, of a listed person, or of the signed-in person."""
        login = (await self.inner.identity(user_token)).login
        rules = self.rules()
        return [
            repo for repo in await self.inner.repositories(user_token) if may_use_repository(rules, repo.owner, login)
        ]

    async def pull_request(self, user_token: str, repo: RepoRef, number: int) -> PullInfo | None:
        """A pull request of a repository that is not served does not exist."""
        login = (await self.inner.identity(user_token)).login
        if not may_use_repository(self.rules(), repo.owner, login):
            return None
        return await self.inner.pull_request(user_token, repo, number)
