"""A tiny result type: failures that the caller is expected to handle are values, not exceptions."""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Ok[T]:
    """A success carrying its value."""

    value: T


@dataclass(frozen=True, slots=True)
class Err[E]:
    """A failure carrying why."""

    error: E


type Result[T, E] = Ok[T] | Err[E]


def map_ok[T, U, E](result: Result[T, E], function: Callable[[T], U]) -> Result[U, E]:
    """Apply ``function`` to a success and leave a failure as it is."""
    match result:
        case Ok(value):
            return Ok(function(value))
        case Err():
            return result
