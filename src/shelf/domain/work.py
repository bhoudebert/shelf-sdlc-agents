"""A piece of work moving through the pipeline, as a pure state machine.

``start`` and ``decide`` take the current state and an event, and return the next state and its commands.
They do no I/O: the workflow engine feeds them events and executes the commands, so the same function is what
production runs and what the tests exercise.
"""

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import NamedTuple, assert_never

from shelf.domain.pipeline import KIND, LOOP_BACK, PIPELINE, Kind, Phase
from shelf.domain.policy import Course


class Verdict(StrEnum):
    """What a reviewer concludes."""

    APPROVE = auto()
    CHANGES = auto()
    ESCALATE = auto()


class DecisionKind(StrEnum):
    """The closed list of things a person can decide. Never interpreted by a model."""

    APPROVE = auto()
    CHANGES = auto()
    RESUME = auto()
    REJECT = auto()
    ABORT = auto()


class Reason(StrEnum):
    """Why a person is being asked."""

    GATE = auto()
    ESCALATION = auto()
    FAILURE = auto()
    MERGE = auto()


class Outcome(StrEnum):
    """How a piece of work ended."""

    MERGED = auto()
    CLOSED = auto()
    ABORTED = auto()


# What a finished step reports.


@dataclass(frozen=True, slots=True)
class Produced:
    """A producing step finished."""


@dataclass(frozen=True, slots=True)
class Reviewed:
    """A reviewing step reached a verdict, with the issues it found."""

    verdict: Verdict
    issues: str = ""


@dataclass(frozen=True, slots=True)
class Verified:
    """The project's checks ran."""

    passed: bool
    report: str = ""


type StepResult = Produced | Reviewed | Verified


# Events: what happens to a piece of work.


@dataclass(frozen=True, slots=True)
class StepDone:
    """The step in progress finished with a result."""

    result: StepResult


@dataclass(frozen=True, slots=True)
class StepFailed:
    """The step in progress failed for good, after its retries."""

    reason: str


@dataclass(frozen=True, slots=True)
class PersonDecided:
    """An authorised person decided. Who may decide is checked before this event exists."""

    by: str
    kind: DecisionKind
    note: str = ""


@dataclass(frozen=True, slots=True)
class PullRequestClosed:
    """The pull request was merged or closed on GitHub."""

    merged: bool


type Event = StepDone | StepFailed | PersonDecided | PullRequestClosed


# States: where a piece of work is.


@dataclass(frozen=True, slots=True)
class Running:
    """An agent or a check is working on ``phase``."""

    phase: Phase
    attempt: int = 0
    feedback: str = ""


@dataclass(frozen=True, slots=True)
class AwaitingPerson:
    """Nothing runs: a person is asked to act."""

    phase: Phase
    reason: Reason
    detail: str = ""


@dataclass(frozen=True, slots=True)
class Finished:
    """The work is over."""

    outcome: Outcome


type State = Running | AwaitingPerson | Finished


# Commands: what the world must do next.


@dataclass(frozen=True, slots=True)
class RunStep:
    """Run the role or the checks of ``phase``, with the feedback that sent the work back, if any."""

    phase: Phase
    attempt: int
    feedback: str


@dataclass(frozen=True, slots=True)
class AskPerson:
    """Tell a person what the work waits for."""

    phase: Phase
    reason: Reason
    detail: str


@dataclass(frozen=True, slots=True)
class CancelStep:
    """Stop the step in progress."""

    phase: Phase


@dataclass(frozen=True, slots=True)
class PublishPullRequest:
    """Open the pull request that carries the work."""


@dataclass(frozen=True, slots=True)
class Conclude:
    """Close the work with its outcome."""

    outcome: Outcome


type Command = RunStep | AskPerson | CancelStep | PublishPullRequest | Conclude


class Transition(NamedTuple):
    """The next state and the commands that lead there."""

    state: State
    commands: tuple[Command, ...] = ()


# Transitions.


def start(course: Course) -> Transition:
    """Begin a piece of work at the first phase of its course."""
    return _enter(course, course.phases[0])


def decide(course: Course, state: State, event: Event) -> Transition:
    """Return what follows ``event`` in ``state``. An event that makes no sense there changes nothing."""
    match state:
        case Finished():
            return Transition(state)
        case Running():
            return _when_running(course, state, event)
        case AwaitingPerson():
            return _when_waiting(course, state, event)
        case _ as unreachable:
            assert_never(unreachable)


def _when_running(course: Course, state: Running, event: Event) -> Transition:
    match event:
        case StepDone(result):
            return _after_step(course, state, result)
        case StepFailed(reason):
            return _ask(state.phase, Reason.FAILURE, reason)
        case PersonDecided(kind=DecisionKind.ABORT):
            return _stop(state.phase, Outcome.ABORTED)
        case PersonDecided(kind=DecisionKind.REJECT):
            return _stop(state.phase, Outcome.CLOSED)
        case PullRequestClosed(merged):
            return _stop(state.phase, _closed(merged=merged))
        case PersonDecided():
            return Transition(state)
        case _ as unreachable:
            assert_never(unreachable)


def _after_step(course: Course, state: Running, result: StepResult) -> Transition:
    kind = KIND[state.phase]
    match kind, result:
        case Kind.PRODUCE, Produced():
            return _advance(course, state.phase, state.attempt)
        case Kind.REVIEW, Reviewed(Verdict.APPROVE):
            return _advance(course, state.phase, 0)
        case Kind.REVIEW, Reviewed(Verdict.CHANGES, issues):
            return _send_back(course, state, issues)
        case Kind.REVIEW, Reviewed(Verdict.ESCALATE, issues):
            return _ask(state.phase, Reason.ESCALATION, issues)
        case Kind.VERIFY, Verified(passed=True):
            return _advance(course, state.phase, state.attempt)
        case Kind.VERIFY, Verified(False, report):
            return _send_back(course, state, report)
        case _:
            return _ask(state.phase, Reason.FAILURE, f"unexpected result for {state.phase}: {result!r}")


def _when_waiting(course: Course, state: AwaitingPerson, event: Event) -> Transition:
    match event:
        case PullRequestClosed(merged):
            return Transition(
                Finished(Outcome.MERGED if merged else Outcome.CLOSED), (Conclude(_closed(merged=merged)),)
            )
        case PersonDecided(kind=DecisionKind.ABORT):
            return _conclude(Outcome.ABORTED)
        case PersonDecided(kind=DecisionKind.REJECT):
            return _conclude(Outcome.CLOSED)
        case PersonDecided(kind=DecisionKind.APPROVE) if state.reason in (Reason.GATE, Reason.ESCALATION):
            return _advance(course, state.phase, 0)
        case PersonDecided(kind=DecisionKind.CHANGES, note=note):
            return _enter(course, LOOP_BACK.get(state.phase, state.phase), feedback=note)
        case PersonDecided(kind=DecisionKind.RESUME, note=note) if state.reason in (
            Reason.ESCALATION,
            Reason.FAILURE,
        ):
            return _enter(course, state.phase, feedback=note)
        case StepDone() | StepFailed() | PersonDecided():
            return Transition(state)
        case _ as unreachable:
            assert_never(unreachable)


def _closed(*, merged: bool) -> Outcome:
    return Outcome.MERGED if merged else Outcome.CLOSED


def _enter(course: Course, phase: Phase, attempt: int = 0, feedback: str = "") -> Transition:
    match KIND[phase]:
        case Kind.GATE:
            return _ask(phase, Reason.GATE, "")
        case Kind.MERGE:
            publish: tuple[Command, ...] = (PublishPullRequest(),) if course.publishes_pull_request else ()
            return Transition(AwaitingPerson(phase, Reason.MERGE), (*publish, AskPerson(phase, Reason.MERGE, "")))
        case Kind.PRODUCE | Kind.REVIEW | Kind.VERIFY:
            return Transition(Running(phase, attempt, feedback), (RunStep(phase, attempt, feedback),))
        case _ as unreachable:
            assert_never(unreachable)


def _advance(course: Course, phase: Phase, attempt: int) -> Transition:
    upcoming = next((p for p in course.phases if PIPELINE.index(p) > PIPELINE.index(phase)), None)
    if upcoming is None:
        return _conclude(Outcome.MERGED)
    return _enter(course, upcoming, attempt)


def _send_back(course: Course, state: Running, feedback: str) -> Transition:
    if state.attempt >= course.max_rounds:
        return _ask(state.phase, Reason.ESCALATION, f"limit of {course.max_rounds} rounds reached:\n{feedback}")
    return _enter(course, LOOP_BACK[state.phase], state.attempt + 1, feedback)


def _ask(phase: Phase, reason: Reason, detail: str) -> Transition:
    return Transition(AwaitingPerson(phase, reason, detail), (AskPerson(phase, reason, detail),))


def _stop(phase: Phase, outcome: Outcome) -> Transition:
    return Transition(Finished(outcome), (CancelStep(phase), Conclude(outcome)))


def _conclude(outcome: Outcome) -> Transition:
    return Transition(Finished(outcome), (Conclude(outcome),))
