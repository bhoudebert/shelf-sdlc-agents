"""A ``Documents`` that remembers what it read for a few seconds, so a page polling every few seconds costs little."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from shelf.domain.model import RepoRef, WorkId
from shelf.ports.documents import Documents


@dataclass(frozen=True, slots=True)
class CachedDocuments:
    """Wraps a ``Documents`` with a short per-work cache."""

    inner: Documents
    ttl_seconds: float = 10.0
    clock: Callable[[], float] = time.monotonic
    _read: dict[str, tuple[float, Mapping[str, str]]] = field(
        default_factory=dict[str, tuple[float, Mapping[str, str]]], repr=False
    )

    async def read(self, repo: RepoRef, work_id: WorkId) -> Mapping[str, str]:
        """The documents, from the cache while it is fresh."""
        key = f"{repo.full_name}:{work_id}"
        found = self._read.get(key)
        if found is not None and self.clock() - found[0] < self.ttl_seconds:
            return found[1]
        documents = await self.inner.read(repo, work_id)
        self._read[key] = (self.clock(), documents)
        return documents
