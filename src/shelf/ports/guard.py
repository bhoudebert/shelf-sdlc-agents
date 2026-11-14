"""How the guard's findings are read."""

from typing import Protocol

from shelf.domain.guard import GuardReport
from shelf.domain.result import Result


class GuardReader(Protocol):
    """Reads what the guard has recorded about the agents."""

    async def report(self) -> Result[GuardReport, str]:
        """The counts of the log, or why it could not be read."""
        ...
