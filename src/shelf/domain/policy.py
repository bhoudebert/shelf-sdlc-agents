"""How a piece of work is configured to run, and the course that results for an entry point."""

from dataclasses import dataclass

from shelf.domain.pipeline import FIRST_PHASE, PIPELINE, EntryPoint, Phase


@dataclass(frozen=True, slots=True)
class Policy:
    """The per-repository choices that shape a run."""

    max_rounds: int = 3
    """How many times a loop may send work back before a person is asked."""
    spec_approval: bool = True
    """Whether a person must approve the spec before the design starts."""
    design_review: bool = True
    """Whether a reviewer checks the design before the plan."""

    def __post_init__(self) -> None:
        """Reject a policy that would never allow a loop."""
        if self.max_rounds < 1:
            message = "max_rounds must be at least 1"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Course:
    """The phases one piece of work will go through, and how it ends."""

    phases: tuple[Phase, ...]
    max_rounds: int
    publishes_pull_request: bool
    """False when the work arrived with a pull request of its own."""


def course_for(entry: EntryPoint, policy: Policy) -> Course:
    """Build the course for ``entry``: the pipeline from its first phase, minus what the policy turns off."""
    skipped = {
        phase
        for phase, enabled in (
            (Phase.SPEC_APPROVAL, policy.spec_approval),
            (Phase.DESIGN_REVIEW, policy.design_review),
        )
        if not enabled
    }
    first = PIPELINE.index(FIRST_PHASE[entry])
    return Course(
        phases=tuple(phase for phase in PIPELINE[first:] if phase not in skipped),
        max_rounds=policy.max_rounds,
        publishes_pull_request=entry is not EntryPoint.PULL_REQUEST_REVIEW,
    )
