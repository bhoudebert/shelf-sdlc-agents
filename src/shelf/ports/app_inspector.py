"""How the GitHub App is looked at: what GitHub says about its events, permissions and webhook."""

from typing import Protocol

from shelf.domain.app_check import AppFacts
from shelf.domain.result import Result


class AppInspector(Protocol):
    """Reads the App's own configuration from GitHub."""

    async def facts(self) -> Result[AppFacts, str]:
        """The App's configuration, or why it could not be read."""
        ...
