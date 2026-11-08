"""What crosses the Temporal boundary: plain data with explicit conversions to and from the domain.

Temporal serialises payloads as JSON, and unions of dataclasses do not survive that. The wire types are therefore
flat and tagged, and the conversions below are the only place that knows both shapes.
"""

from dataclasses import dataclass

from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Course, Policy, course_for
from shelf.domain.work import (
    AwaitingPerson,
    DecisionKind,
    Event,
    Finished,
    PersonDecided,
    Produced,
    PullRequestClosed,
    Reviewed,
    Running,
    State,
    StepResult,
    Verdict,
    Verified,
)


@dataclass(frozen=True, slots=True)
class WorkInput:
    """The input of the workflow: the request, the policy, and how often to look at GitHub."""

    work_id: str
    repo: str
    requester: str
    entry: str
    text: str = ""
    pull_request: int | None = None
    max_rounds: int = 3
    spec_approval: bool = True
    design_review: bool = True
    poll_base_seconds: float = 30.0
    poll_ceiling_seconds: float = 900.0


@dataclass(frozen=True, slots=True)
class StepInput:
    """The input of the activity that runs a step."""

    work: WorkInput
    phase: str
    attempt: int
    feedback: str


@dataclass(frozen=True, slots=True)
class StepOutput:
    """What a step reports, as a tagged record."""

    kind: str
    verdict: str = ""
    passed: bool = False
    text: str = ""


@dataclass(frozen=True, slots=True)
class AskInput:
    """The input of the activity that announces a wait."""

    work: WorkInput
    phase: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class EventDto:
    """An event found on the pull request, as a tagged record."""

    kind: str
    merged: bool = False
    by: str = ""
    decision: str = ""
    note: str = ""


@dataclass(frozen=True, slots=True)
class DecisionDto:
    """A person's decision, as the signal carries it."""

    by: str
    kind: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class Snapshot:
    """What the workflow answers when asked where the work is."""

    phase: str
    waiting_for: str = ""
    detail: str = ""
    outcome: str = ""
    pull_request_url: str = ""


def course_of(work: WorkInput) -> Course:
    """The course of the work, from its policy and entry point."""
    policy = Policy(work.max_rounds, work.spec_approval, work.design_review)
    return course_for(EntryPoint(work.entry), policy)


def context_of(work: WorkInput) -> WorkContext:
    """The context a step runs with."""
    request = WorkRequest(
        RepoRef.parse(work.repo), work.requester, EntryPoint(work.entry), work.text, work.pull_request
    )
    return WorkContext(WorkId(work.work_id), request)


def result_of(output: StepOutput) -> StepResult:
    """Read a step's report; raise ``ValueError`` on a kind nobody knows."""
    match output.kind:
        case "produced":
            return Produced()
        case "reviewed":
            return Reviewed(Verdict(output.verdict), output.text)
        case "verified":
            return Verified(output.passed, output.text)
        case other:
            message = f"unknown step result kind: {other!r}"
            raise ValueError(message)


def output_of(result: StepResult) -> StepOutput:
    """Write a step's report."""
    match result:
        case Produced():
            return StepOutput("produced")
        case Reviewed(verdict, issues):
            return StepOutput("reviewed", verdict=verdict, text=issues)
        case Verified(passed, report):
            return StepOutput("verified", passed=passed, text=report)


def event_of(dto: EventDto) -> Event | None:
    """Read an event found on the pull request; ``None`` for a kind this version does not know."""
    match dto.kind:
        case "closed":
            return PullRequestClosed(merged=dto.merged)
        case "decided":
            return PersonDecided(dto.by, DecisionKind(dto.decision), dto.note)
        case _:
            return None


def dto_of(event: Event) -> EventDto | None:
    """Write an event found on the pull request; ``None`` for events that never come from there."""
    match event:
        case PullRequestClosed(merged):
            return EventDto("closed", merged=merged)
        case PersonDecided(by, kind, note):
            return EventDto("decided", by=by, decision=kind, note=note)
        case _:
            return None


def decision_of(dto: DecisionDto) -> PersonDecided:
    """Read a decision signal."""
    return PersonDecided(dto.by, DecisionKind(dto.kind), dto.note)


def snapshot_of(state: State, last_phase: Phase, pull_request_url: str) -> Snapshot:
    """Describe ``state`` for the board; ``last_phase`` is where a finished piece of work ended."""
    match state:
        case Running(phase):
            return Snapshot(phase, pull_request_url=pull_request_url)
        case AwaitingPerson(phase, reason, detail):
            return Snapshot(phase, waiting_for=reason, detail=detail, pull_request_url=pull_request_url)
        case Finished(outcome):
            return Snapshot(last_phase, outcome=outcome, pull_request_url=pull_request_url)
