"""Sessions: a signed cookie carries a random id; the person's GitHub token stays on the server.

There is no user table. A session lives in memory for as long as the person's token does, so a restart signs people
out, which is the price of never writing their tokens anywhere.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from shelf.domain.model import Identity

LIFETIME = timedelta(hours=8)
"""A GitHub App user token lives eight hours."""


@dataclass(frozen=True, slots=True)
class Session:
    """A signed-in person and the token to act as them on GitHub."""

    identity: Identity
    user_token: str
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class SessionStore:
    """Sessions in memory, expiring with the clock that is passed in."""

    clock: Callable[[], datetime] = _now
    _sessions: dict[str, Session] = field(default_factory=dict[str, Session])

    def create(self, identity: Identity, user_token: str) -> str:
        """Start a session and return the id for the cookie."""
        session_id = secrets.token_urlsafe(32)
        self._sessions[session_id] = Session(identity, user_token, self.clock() + LIFETIME)
        return session_id

    def get(self, session_id: str | None) -> Session | None:
        """The live session for ``session_id``; an expired one is forgotten."""
        if session_id is None:
            return None
        session = self._sessions.get(session_id)
        if session is not None and session.expires_at <= self.clock():
            del self._sessions[session_id]
            return None
        return session

    def end(self, session_id: str | None) -> None:
        """Forget a session."""
        if session_id is not None:
            self._sessions.pop(session_id, None)
