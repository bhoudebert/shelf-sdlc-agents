"""The documents a piece of work leaves in its repository: the request, the spec, the design and the plan."""

from collections.abc import Mapping
from typing import Protocol

from shelf.domain.model import RepoRef, WorkId


class Documents(Protocol):
    """Reads what the agents wrote, from the work's branch."""

    async def read(self, repo: RepoRef, work_id: WorkId) -> Mapping[str, str]:
        """The documents that exist so far, by file name. A document not written yet is simply absent."""
        ...
