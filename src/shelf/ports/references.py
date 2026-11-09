"""Reading existing material a piece of work starts from."""

from typing import Protocol

from shelf.domain.model import RepoRef
from shelf.domain.reference import Imported, Reference
from shelf.domain.result import Result


class References(Protocol):
    """Reads an issue, a pull request or a file of a repository."""

    async def read(self, repo: RepoRef, reference: Reference) -> Result[Imported, str]:
        """What the reference says, or a sentence saying why it cannot be used."""
        ...
