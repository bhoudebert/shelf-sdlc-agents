"""The code forge (GitHub) as the application needs it on behalf of a signed-in person."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.model import Identity, RepoRef


class Forge(Protocol):
    """What a person's own GitHub token lets the application see."""

    async def exchange_code(self, code: str) -> str:
        """Trade the OAuth ``code`` from the sign-in redirect for the person's token."""
        ...

    async def identity(self, user_token: str) -> Identity:
        """Who the token belongs to, with the organisations they belong to."""
        ...

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        """The repositories the app is installed on that this person can also access."""
        ...
