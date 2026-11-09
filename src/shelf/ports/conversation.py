"""The conversation on a pull request, read back: what the agents said and what people wrote."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.model import RepoRef
from shelf.domain.story import Message


class Conversations(Protocol):
    """Reads the comments of a pull request as a story."""

    async def read(self, repo: RepoRef, pull_request: int) -> Sequence[Message]:
        """The comments, oldest first, without the one progress comment that the timeline already tells."""
        ...
