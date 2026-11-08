"""The stage label a pull request carries while the work moves: what is happening, in a few words."""

from dataclasses import dataclass
from enum import StrEnum, auto

from shelf.domain.pipeline import Phase
from shelf.domain.work import Reason

PREFIX = "shelf: "


class Tone(StrEnum):
    """How a stage is coloured: working, waiting for a person, or ready for the last word."""

    WORKING = auto()
    WAITING = auto()
    READY = auto()


@dataclass(frozen=True, slots=True)
class Stage:
    """A label's name and colour (hex, no hash)."""

    name: str
    color: str


COLORS: dict[Tone, str] = {Tone.WORKING: "0f2e25", Tone.WAITING: "c1301a", Tone.READY: "2da44e"}

RUNNING_NAMES: dict[Phase, str] = {
    Phase.INTAKE: "writing the spec",
    Phase.SPEC_REVIEW: "reviewing the spec",
    Phase.SPEC_APPROVAL: "spec approval",
    Phase.DESIGN: "designing",
    Phase.DESIGN_REVIEW: "reviewing the design",
    Phase.PLAN: "planning",
    Phase.IMPLEMENT: "implementing",
    Phase.VERIFY: "running checks",
    Phase.CODE_REVIEW: "reviewing the code",
    Phase.PULL_REQUEST: "ready for review",
}


def stage_of(phase: Phase, waiting: Reason | None) -> Stage:
    """The stage for work at ``phase``: running it, or waiting for a person for ``waiting``."""
    if waiting is Reason.MERGE:
        return Stage(f"{PREFIX}ready to merge", COLORS[Tone.READY])
    if waiting is not None:
        return Stage(f"{PREFIX}needs you: {RUNNING_NAMES[phase]}", COLORS[Tone.WAITING])
    return Stage(f"{PREFIX}{RUNNING_NAMES[phase]}", COLORS[Tone.WORKING])
