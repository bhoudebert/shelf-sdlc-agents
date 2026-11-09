"""A ``Forge`` that remembers what GitHub said for a short while.

The board refreshes every few seconds for every open browser tab, and each refresh needs the repositories a person can
see. Asking GitHub every time is slow and spends the rate limit; a minute-old answer is fine for a board.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from shelf.domain.model import Identity, PullInfo, RepoRef
from shelf.ports.forge import Forge


@dataclass(frozen=True, slots=True)
class CachedForge:
    """Wraps a ``Forge``: sign-in is passed through, repository and identity lookups are cached per token."""

    inner: Forge
    ttl_seconds: float = 60.0
    clock: Callable[[], float] = time.monotonic
    _repositories: dict[str, tuple[float, Sequence[RepoRef]]] = field(
        default_factory=dict[str, tuple[float, Sequence[RepoRef]]], repr=False
    )
    _identities: dict[str, tuple[float, Identity]] = field(
        default_factory=dict[str, tuple[float, Identity]], repr=False
    )

    async def exchange_code(self, code: str) -> str:
        """Never cached: a code is used once."""
        return await self.inner.exchange_code(code)

    async def pull_request(self, user_token: str, repo: RepoRef, number: int) -> PullInfo | None:
        """Never cached: a pull request may be opened or closed a moment after the person looks."""
        return await self.inner.pull_request(user_token, repo, number)

    async def identity(self, user_token: str) -> Identity:
        """Who the token belongs to, from the cache while it is fresh."""
        found = self._identities.get(user_token)
        if found is not None and self.clock() - found[0] < self.ttl_seconds:
            return found[1]
        identity = await self.inner.identity(user_token)
        self._identities[user_token] = (self.clock(), identity)
        return identity

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        """The repositories this person can see, from the cache while it is fresh."""
        found = self._repositories.get(user_token)
        if found is not None and self.clock() - found[0] < self.ttl_seconds:
            return found[1]
        repositories = await self.inner.repositories(user_token)
        self._repositories[user_token] = (self.clock(), repositories)
        return repositories
