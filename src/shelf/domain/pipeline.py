"""The software-development pipeline as data, and where a piece of work enters it."""

from enum import StrEnum, auto


class Phase(StrEnum):
    """One step of the pipeline, in the order the work flows through them."""

    INTAKE = auto()
    SPEC_REVIEW = auto()
    SPEC_APPROVAL = auto()
    DESIGN = auto()
    DESIGN_REVIEW = auto()
    PLAN = auto()
    IMPLEMENT = auto()
    VERIFY = auto()
    CODE_REVIEW = auto()
    PULL_REQUEST = auto()


PIPELINE: tuple[Phase, ...] = tuple(Phase)
"""Every phase, in flow order."""


class Kind(StrEnum):
    """What a phase does, which decides how a piece of work moves through it."""

    PRODUCE = auto()
    """An agent writes a document or the code."""
    REVIEW = auto()
    """An agent on another model judges what the previous phase produced."""
    VERIFY = auto()
    """The project's own checks run."""
    GATE = auto()
    """A person approves before the work goes on."""
    MERGE = auto()
    """The pull request is open and a person has the last word."""


KIND: dict[Phase, Kind] = {
    Phase.INTAKE: Kind.PRODUCE,
    Phase.SPEC_REVIEW: Kind.REVIEW,
    Phase.SPEC_APPROVAL: Kind.GATE,
    Phase.DESIGN: Kind.PRODUCE,
    Phase.DESIGN_REVIEW: Kind.REVIEW,
    Phase.PLAN: Kind.PRODUCE,
    Phase.IMPLEMENT: Kind.PRODUCE,
    Phase.VERIFY: Kind.VERIFY,
    Phase.CODE_REVIEW: Kind.REVIEW,
    Phase.PULL_REQUEST: Kind.MERGE,
}
"""The kind of every phase."""

LOOP_BACK: dict[Phase, Phase] = {
    Phase.SPEC_REVIEW: Phase.INTAKE,
    Phase.SPEC_APPROVAL: Phase.INTAKE,
    Phase.DESIGN_REVIEW: Phase.DESIGN,
    Phase.VERIFY: Phase.IMPLEMENT,
    Phase.CODE_REVIEW: Phase.IMPLEMENT,
    Phase.PULL_REQUEST: Phase.IMPLEMENT,
}
"""The phase that redoes the work when a reviewer, a check or a person asks for changes."""


class EntryPoint(StrEnum):
    """Where a person can start: each entry skips the phases already done elsewhere."""

    NEED = auto()
    SPEC = auto()
    DESIGN = auto()
    PLAN = auto()
    IMPLEMENT = auto()
    PULL_REQUEST_REVIEW = auto()
    PULL_REQUEST_WORK = auto()


FIRST_PHASE: dict[EntryPoint, Phase] = {
    EntryPoint.NEED: Phase.INTAKE,
    EntryPoint.SPEC: Phase.SPEC_REVIEW,
    EntryPoint.DESIGN: Phase.DESIGN,
    EntryPoint.PLAN: Phase.PLAN,
    EntryPoint.IMPLEMENT: Phase.IMPLEMENT,
    EntryPoint.PULL_REQUEST_REVIEW: Phase.CODE_REVIEW,
    EntryPoint.PULL_REQUEST_WORK: Phase.IMPLEMENT,
}
"""The phase at which each entry point joins the pipeline."""


def phases_from(entry: EntryPoint) -> tuple[Phase, ...]:
    """Return the phases a piece of work goes through when started at ``entry``."""
    return PIPELINE[PIPELINE.index(FIRST_PHASE[entry]) :]
