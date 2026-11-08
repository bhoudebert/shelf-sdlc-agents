"""How often to look at GitHub while work waits: often at first, then less and less."""

from datetime import timedelta
from enum import StrEnum, auto


def next_interval(current: timedelta, ceiling: timedelta, factor: float = 2.0) -> timedelta:
    """Grow ``current`` by ``factor`` without passing ``ceiling``.

    A long wait (a person who answers tomorrow) then costs a few dozen history events instead of thousands.
    """
    return min(current * factor, ceiling)


class Mode(StrEnum):
    """Who wakes waiting work."""

    LOCAL = auto()
    """No public address: only the poll looks at GitHub."""
    SERVER = auto()
    """GitHub webhooks wake the work; the poll is a slow safety net."""


def poll_bounds(mode: Mode) -> tuple[timedelta, timedelta]:
    """The first and the longest interval between looks at GitHub for ``mode``."""
    if mode is Mode.LOCAL:
        return timedelta(seconds=30), timedelta(minutes=15)
    return timedelta(minutes=5), timedelta(hours=1)
