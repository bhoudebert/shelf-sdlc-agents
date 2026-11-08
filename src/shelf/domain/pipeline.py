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


class EntryPoint(StrEnum):
    """Where a person can start: each entry skips the phases already done elsewhere."""

    NEED = auto()
    SPEC = auto()
    DESIGN = auto()
    PLAN = auto()
    IMPLEMENT = auto()
    PULL_REQUEST_REVIEW = auto()


FIRST_PHASE: dict[EntryPoint, Phase] = {
    EntryPoint.NEED: Phase.INTAKE,
    EntryPoint.SPEC: Phase.SPEC_REVIEW,
    EntryPoint.DESIGN: Phase.DESIGN,
    EntryPoint.PLAN: Phase.PLAN,
    EntryPoint.IMPLEMENT: Phase.IMPLEMENT,
    EntryPoint.PULL_REQUEST_REVIEW: Phase.CODE_REVIEW,
}
"""The phase at which each entry point joins the pipeline."""


def phases_from(entry: EntryPoint) -> tuple[Phase, ...]:
    """Return the phases a piece of work goes through when started at ``entry``."""
    return PIPELINE[PIPELINE.index(FIRST_PHASE[entry]) :]
