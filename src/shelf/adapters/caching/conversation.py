"""A ``Conversations`` that remembers what it read for a few seconds, so a page polling costs little."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from shelf.domain.model import RepoRef
from shelf.domain.story import Message
from shelf.ports.conversation import Conversations


@dataclass(frozen=True, slots=True)
class CachedConversations:
    """Wraps a ``Conversations`` with a short per-pull-request cache."""

    inner: Conversations
    ttl_seconds: float = 10.0
    clock: Callable[[], float] = time.monotonic
    _read: dict[str, tuple[float, Sequence[Message]]] = field(
        default_factory=dict[str, tuple[float, Sequence[Message]]], repr=False
    )
    _described: dict[str, tuple[float, str]] = field(default_factory=dict[str, tuple[float, str]], repr=False)

    async def description(self, repo: RepoRef, pull_request: int) -> str:
        """The description, from the cache while it is fresh."""
        key = f"{repo.full_name}#{pull_request}"
        found = self._described.get(key)
        if found is not None and self.clock() - found[0] < self.ttl_seconds:
            return found[1]
        text = await self.inner.description(repo, pull_request)
        self._described[key] = (self.clock(), text)
        return text

    async def read(self, repo: RepoRef, pull_request: int) -> Sequence[Message]:
        """The conversation, from the cache while it is fresh."""
        key = f"{repo.full_name}#{pull_request}"
        found = self._read.get(key)
        if found is not None and self.clock() - found[0] < self.ttl_seconds:
            return found[1]
        story = await self.inner.read(repo, pull_request)
        self._read[key] = (self.clock(), story)
        return story
