"""How often to look at GitHub while work waits: often at first, then less and less."""

from datetime import timedelta


def next_interval(current: timedelta, ceiling: timedelta, factor: float = 2.0) -> timedelta:
    """Grow ``current`` by ``factor`` without passing ``ceiling``.

    A long wait (a person who answers tomorrow) then costs a few dozen history events instead of thousands.
    """
    return min(current * factor, ceiling)
