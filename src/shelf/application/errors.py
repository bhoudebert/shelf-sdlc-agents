"""The ways a use case can refuse, as values the entry points translate for the person."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NotAllowed:
    """The person may not do this."""

    reason: str


@dataclass(frozen=True, slots=True)
class NotFound:
    """What was asked for does not exist, or is not visible to this person."""

    what: str


@dataclass(frozen=True, slots=True)
class Invalid:
    """The request is not well formed."""

    reason: str


type Refusal = NotAllowed | NotFound | Invalid
