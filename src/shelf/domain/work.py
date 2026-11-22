"""A piece of work moving through the pipeline, as a pure state machine.

``start`` and ``decide`` take the current state and an event, and return the next state and its commands.
They do no I/O: the workflow engine feeds them events and executes the commands, so the same function is what
production runs and what the tests exercise.
"""

import re
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from typing import NamedTuple, assert_never

from shelf.domain.brief import DISPUTE_MARK
from shelf.domain.pipeline import KIND, LOOP_BACK, PIPELINE, Kind, Phase
from shelf.domain.policy import Course
from shelf.domain.usage import Usage


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


class ArbitrationVerdict(StrEnum):
    """What an arbitrator concludes about a disagreement (ADR 0021)."""

    FIX = auto()
    """The reviewer is right: the author is sent back with the arbitrator's instructions."""
    OVERRULE = auto()
    """The reviewer is wrong or out of scope: the work goes on."""
    ESCALATE = auto()
    """Only a person can decide, or no evidence settles it."""


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

    usage: Usage | None = None
    """What the agent used, when the provider said."""
    session: str = ""
    """The session the agent ran in, so that a later round can continue it."""


@dataclass(frozen=True, slots=True)
class Reviewed:
    """A reviewing step reached a verdict, with the issues it found."""

    verdict: Verdict
    issues: str = ""
    usage: Usage | None = None
    """What the agent used, when the provider said."""
    session: str = ""
    """The session the agent ran in, so that a later round can continue it."""
    repeated: int = 0
    """How many points raised in an earlier round are still unaddressed."""
    blocking: bool = True
    """Whether any open point must be fixed before the work can merge."""


@dataclass(frozen=True, slots=True)
class Verified:
    """The project's checks ran."""

    passed: bool
    report: str = ""
    waiting: bool = False
    """The repository's CI has not finished: look again later, without counting a round."""


@dataclass(frozen=True, slots=True)
class Arbitrated:
    """An arbitrator settled a disagreement, or said that it cannot."""

    verdict: ArbitrationVerdict
    text: str = ""
    """The instructions of a fix, the evidence of an overrule, or the brief for a person."""
    usage: Usage | None = None
    session: str = ""


WAITING_FOR_CI = "waiting for CI"
"""The feedback of a checks step that only looks at the CI again: the local commands already passed."""

type StepResult = Produced | Reviewed | Verified | Arbitrated


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
    failed: str = ""
    """How the checks' last failure looked (``fingerprint``): empty when they have not failed, or since they passed."""
    same: int = 0
    """How many times in a row the checks failed that way."""
    fixes: int = 0
    """How many times the checks sent the work back: those rounds are not the code review's."""
    arbitrated: tuple[Phase, ...] = ()
    """The phases whose deadlock an arbitrator already looked at: it looks at each once (ADR 0021)."""


@dataclass(frozen=True, slots=True)
class Arbitrating:
    """An arbitrator is reading a disagreement; ``was`` is where the work stood when it began."""

    was: Running
    issues: str
    blocking: bool = True


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


type State = Running | Arbitrating | AwaitingPerson | Finished


# Commands: what the world must do next.


@dataclass(frozen=True, slots=True)
class RunStep:
    """Run the role or the checks of ``phase``, with the feedback that sent the work back, if any."""

    phase: Phase
    attempt: int
    feedback: str
    session: str = ""
    """The agent's session from an earlier round, to continue; empty when it has none."""
    arbitrates: bool = False
    """Only inside the application: this run is the arbitrator's, about the disagreement of ``phase``."""


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
class SetPullRequestReady:
    """Mark the pull request ready for review (``ready``), or back to draft while agents rework it."""

    ready: bool


@dataclass(frozen=True, slots=True)
class Conclude:
    """Close the work with its outcome."""

    outcome: Outcome


@dataclass(frozen=True, slots=True)
class NoteOpenPoints:
    """Say on the pull request which issues of a review stayed open when the work went on without a person."""

    phase: Phase
    issues: str


@dataclass(frozen=True, slots=True)
class Arbitrate:
    """Run the arbitrator on the disagreement of ``phase``, with the issues that could not be settled."""

    phase: Phase
    issues: str


@dataclass(frozen=True, slots=True)
class RecordArbitration:
    """Write an arbitration into the decision log of the work, and say it on the pull request."""

    phase: Phase
    verdict: ArbitrationVerdict
    text: str


type Command = (
    RunStep
    | AskPerson
    | CancelStep
    | PublishPullRequest
    | SetPullRequestReady
    | Conclude
    | NoteOpenPoints
    | Arbitrate
    | RecordArbitration
)


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
        case Arbitrating():
            return _when_arbitrating(course, state, event)
        case AwaitingPerson():
            return _when_waiting(course, state, event)
        case _ as unreachable:
            assert_never(unreachable)


def _when_running(course: Course, state: Running, event: Event) -> Transition:
    match event:
        case StepDone(result):
            moved = _remembering(course, state, _after_step(course, state, result))
            return _with_publication(course, state, _carrying_arbitrations(state, moved))
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


CHECK_REPEATS = 3
"""How many times in a row the same failure of the checks is tried again before a person is asked."""
CHECK_CEILING = 10
"""The checks loop ends at this many times the maximum number of rounds, so that it cannot run without end."""

_NUMBER = re.compile(r"\b[0-9a-f]{12,}\b|[0-9]+")


def fingerprint(report: str) -> str:
    """What a failure of the checks looks like, without what changes between runs: numbers, timings, identifiers.

    Two reports that give the same fingerprint are the same failure.
    """
    return " ".join(_NUMBER.sub("#", report).split())


def _remembering(course: Course, state: Running, moved: Transition) -> Transition:
    """Keep, across the phases, what the checks loop remembers: how it failed last and how many rounds it used."""
    if not course.judges_check_loops or not isinstance(moved.state, Running):
        return moved
    after = moved.state
    if after.failed or after.same or after.fixes:  # the checks have just set them
        return moved
    passed = KIND[state.phase] is Kind.VERIFY and moved.state.phase is not state.phase
    keep = {"fixes": state.fixes} if passed else {"failed": state.failed, "same": state.same, "fixes": state.fixes}
    return Transition(replace(after, **keep), moved.commands)


def _carrying_arbitrations(state: Running, moved: Transition) -> Transition:
    """Keep, across the phases, which deadlocks an arbitrator already looked at."""
    if not state.arbitrated or not isinstance(moved.state, Running) or moved.state.arbitrated:
        return moved
    return Transition(replace(moved.state, arbitrated=state.arbitrated), moved.commands)


def _when_arbitrating(course: Course, state: Arbitrating, event: Event) -> Transition:
    """What follows while an arbitrator reads a disagreement: its verdict, or the same ends as for a running step."""
    was = state.was
    match event:
        case StepDone(Arbitrated(verdict, text)):
            return _after_arbitration(course, state, verdict, text)
        case StepFailed():
            return _unsettled(course, was.phase, state.issues, blocking=state.blocking)
        case PersonDecided(kind=DecisionKind.ABORT):
            return _stop(was.phase, Outcome.ABORTED)
        case PersonDecided(kind=DecisionKind.REJECT):
            return _stop(was.phase, Outcome.CLOSED)
        case PullRequestClosed(merged):
            return _stop(was.phase, _closed(merged=merged))
        case StepDone() | PersonDecided():
            return Transition(state)
        case _ as unreachable:
            assert_never(unreachable)


FIX_PREFIX = (
    "An arbitrator settled the disagreement and found the reviewer right. Do exactly what follows, as your only task. "
    "Run each proof it names and report its result in your answer."
)


def _after_arbitration(course: Course, state: Arbitrating, verdict: ArbitrationVerdict, text: str) -> Transition:
    was = state.was
    phase = was.phase
    done = (*was.arbitrated, phase)
    record = RecordArbitration(phase, verdict, text)
    if verdict is ArbitrationVerdict.OVERRULE and KIND[phase] is not Kind.REVIEW:
        verdict = ArbitrationVerdict.ESCALATE  # a failing check is never overruled
    match verdict:
        case ArbitrationVerdict.FIX:
            back = _enter(course, LOOP_BACK[phase], was.attempt + 1, f"{FIX_PREFIX}\n\n{text}")
            if isinstance(back.state, Running):
                carried = replace(back.state, failed=was.failed, same=was.same, fixes=was.fixes, arbitrated=done)
                back = Transition(carried, back.commands)
            return Transition(back.state, (record, *back.commands))
        case ArbitrationVerdict.OVERRULE:
            moved = _advance(course, phase, 0)
            if isinstance(moved.state, Running):
                moved = Transition(replace(moved.state, arbitrated=done), moved.commands)
            return Transition(moved.state, (record, *moved.commands))
        case ArbitrationVerdict.ESCALATE:
            unsettled = _unsettled(course, phase, state.issues, blocking=state.blocking, brief=text)
            return Transition(unsettled.state, (record, *unsettled.commands))


def _with_publication(course: Course, state: Running, transition: Transition) -> Transition:
    """Open the pull request as soon as the first step is done, so that everything after it happens in the open.

    Asking again is harmless: the adapter returns the pull request that already exists.
    """
    if not course.opens_early or not course.publishes_pull_request or state.phase is not course.phases[0]:
        return transition
    if isinstance(transition.state, Finished) or PublishPullRequest() in transition.commands:
        return transition
    return Transition(transition.state, (PublishPullRequest(), *transition.commands))


def _after_step(course: Course, state: Running, result: StepResult) -> Transition:
    kind = KIND[state.phase]
    match kind, result:
        case Kind.PRODUCE, Produced():
            return _advance(course, state.phase, state.attempt)
        case Kind.REVIEW, Reviewed(Verdict.APPROVE):
            return _advance(course, state.phase, 0)
        case Kind.REVIEW, Reviewed(Verdict.CHANGES, issues) if course.asks_a_person_after_review:
            return _ask(state.phase, Reason.ESCALATION, issues)
        case Kind.REVIEW, Reviewed(Verdict.CHANGES, issues) as review:
            return _send_back(course, state, issues, review)
        case Kind.REVIEW, Reviewed(Verdict.ESCALATE, issues, blocking=blocking):
            return _deadlocked(course, state, issues, blocking=blocking)
        case Kind.VERIFY | Kind.MERGE, Verified() as seen:
            return _after_checks(course, state, seen)
        case _:
            return _ask(state.phase, Reason.FAILURE, f"unexpected result for {state.phase}: {result!r}")


def _after_checks(course: Course, state: Running, seen: Verified) -> Transition:
    """What the checks, or the CI seen once the pull request is ready, decide."""
    at_merge = KIND[state.phase] is Kind.MERGE
    if seen.waiting and (at_merge or course.waits_for_ci):
        if at_merge:
            return Transition(state, (RunStep(state.phase, state.attempt, WAITING_FOR_CI),))  # look again, same round
        return _enter(course, state.phase, state.attempt, feedback=WAITING_FOR_CI)
    if seen.waiting or seen.passed:
        return _ask(state.phase, Reason.MERGE, "") if at_merge else _advance(course, state.phase, state.attempt)
    back = (
        _send_checks_back(course, state, seen.report)
        if course.judges_check_loops
        else _send_back(course, state, seen.report)
    )
    return Transition(back.state, (SetPullRequestReady(ready=False), *back.commands)) if at_merge else back


def _send_checks_back(course: Course, state: Running, report: str) -> Transition:
    """Send a failing check back to the implementer; ask a person when it fails the same way again and again."""
    failed = fingerprint(report)
    same = state.same + 1 if failed == state.failed else 1
    fixes = state.fixes + 1
    if same >= CHECK_REPEATS:
        detail = f"the checks failed the same way {same} times in a row:\n{report}"
        return _deadlocked(course, state, detail)
    limit = course.max_rounds * CHECK_CEILING
    if fixes >= limit:
        return _deadlocked(course, state, f"limit of {limit} rounds reached:\n{report}")
    back = _enter(course, LOOP_BACK[state.phase], state.attempt + 1, report)
    if isinstance(back.state, Running):
        back = Transition(replace(back.state, failed=failed, same=same, fixes=fixes), back.commands)
    return back


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
            return _approved(course, state)
        case PersonDecided(kind=DecisionKind.CHANGES, note=note):
            if course.asks_a_person_after_review and not course.review_is_read_only and not note.strip():
                # hand over the reviewer's own findings
                note = state.detail
            target = Phase.CODE_REVIEW if course.review_is_read_only else LOOP_BACK.get(state.phase, state.phase)
            back = _enter(course, target, feedback=note)
            if state.reason is Reason.MERGE and course.readies_pull_request:  # back to draft while agents rework it
                return Transition(back.state, (SetPullRequestReady(ready=False), *back.commands))
            return back
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
            publish: tuple[Command, ...] = ()
            if course.publishes_pull_request:
                publish = (PublishPullRequest(), *((SetPullRequestReady(ready=True),) if course.opens_early else ()))
            elif course.adopts_pull_request:
                publish = (SetPullRequestReady(ready=True),)
            if course.looks_at_ci_before_merge:  # what marking it ready started must finish first
                return Transition(Running(phase, attempt, feedback), (*publish, RunStep(phase, attempt, feedback)))
            return Transition(AwaitingPerson(phase, Reason.MERGE), (*publish, AskPerson(phase, Reason.MERGE, "")))
        case Kind.PRODUCE | Kind.REVIEW | Kind.VERIFY:
            return Transition(Running(phase, attempt, feedback), (RunStep(phase, attempt, feedback),))
        case _ as unreachable:
            assert_never(unreachable)


def _approved(course: Course, state: AwaitingPerson) -> Transition:
    moved = _advance(course, state.phase, 0)
    if state.reason is Reason.ESCALATION and course.approval_counts_for_the_gate:
        return _past_gate(course, moved)
    return moved


def _past_gate(course: Course, moved: Transition) -> Transition:
    """Skip the gate that a person's acceptance of the escalated review just before it already answered."""
    if isinstance(moved.state, AwaitingPerson) and moved.state.reason is Reason.GATE:
        return _advance(course, moved.state.phase, 0)
    return moved


def _advance(course: Course, phase: Phase, attempt: int) -> Transition:
    upcoming = next((p for p in course.phases if PIPELINE.index(p) > PIPELINE.index(phase)), None)
    if upcoming is None:
        return _conclude(Outcome.MERGED)
    return _enter(course, upcoming, attempt)


def _send_back(course: Course, state: Running, feedback: str, review: Reviewed | None = None) -> Transition:
    """Send the work back, or end the loop: a reviewer's repeated point or a count of rounds that ran out."""
    judges = course.judges_review_loops and review is not None
    blocking = review.blocking if review else True
    if review and judges and review.repeated > 0:
        detail = f"the reviewer and the author disagree, {review.repeated} point(s) came back:\n{feedback}"
        return _deadlocked(course, state, detail, blocking=blocking)
    limit = course.max_rounds * 2 if judges else course.max_rounds
    used = state.attempt - state.fixes if course.judges_check_loops else state.attempt
    if used >= limit:
        return _deadlocked(course, state, f"limit of {limit} rounds reached:\n{feedback}", blocking=blocking)
    return _enter(course, LOOP_BACK[state.phase], state.attempt + 1, feedback)


PASSABLE = frozenset({Phase.SPEC_REVIEW, Phase.DESIGN_REVIEW})
"""The reviews of documents: the only ones whose open issues may be passed on. Code review and checks never are."""


def _minor(course: Course, phase: Phase, *, blocking: bool) -> bool:
    """Whether a code review's open points are all minor: the work goes on, with nobody asked and nothing to settle."""
    return course.judges_review_loops and phase is Phase.CODE_REVIEW and not blocking


def _deadlocked(course: Course, state: Running, issues: str, *, blocking: bool = True) -> Transition:
    """A review cannot settle: an arbitrator reads it first when the work asked for one, once for each phase."""
    phase = state.phase
    if course.arbitrates and phase not in state.arbitrated and not _minor(course, phase, blocking=blocking):
        return Transition(Arbitrating(state, issues, blocking), (Arbitrate(phase, issues),))
    return _unsettled(course, phase, issues, blocking=blocking)


def _unsettled(course: Course, phase: Phase, issues: str, *, blocking: bool = True, brief: str = "") -> Transition:
    """A disagreement nobody settled: a person is asked, unless the work may go on, and then its open issues are noted.

    ``brief`` is what the arbitrator said when it could not decide: the person, or the pull request, gets it first.
    """
    said = f"{brief}{DISPUTE_MARK}{issues}" if brief else issues
    if _minor(course, phase, blocking=blocking) or (course.proceeds_on_deadlock and phase in PASSABLE):
        moved = _advance(course, phase, 0)
        return Transition(moved.state, (NoteOpenPoints(phase, said), *moved.commands))
    return _ask(phase, Reason.ESCALATION, said)


def _ask(phase: Phase, reason: Reason, detail: str) -> Transition:
    return Transition(AwaitingPerson(phase, reason, detail), (AskPerson(phase, reason, detail),))


def _stop(phase: Phase, outcome: Outcome) -> Transition:
    return Transition(Finished(outcome), (CancelStep(phase), Conclude(outcome)))


def _conclude(outcome: Outcome) -> Transition:
    return Transition(Finished(outcome), (Conclude(outcome),))
