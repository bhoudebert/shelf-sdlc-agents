"""Reading other repositories as reference material, to put next to the repository a piece of work is on."""

from pathlib import Path
from typing import Protocol

from shelf.domain.context_repo import ContextRepo
from shelf.domain.result import Result


class ContextSources(Protocol):
    """Where reference repositories are read from."""

    async def check(self, item: ContextRepo) -> str:
        """Why ``item`` cannot be read, or an empty string when it can."""
        ...

    async def copy_into(self, item: ContextRepo, destination: Path) -> Result[int, str]:
        """Put read-only copies of the text files of ``item`` into ``destination``; how many, or why not."""
        ...
