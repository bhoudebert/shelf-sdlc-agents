"""What crosses the Temporal boundary: plain data with explicit conversions to and from the domain.

Temporal serialises payloads as JSON, and unions of dataclasses do not survive that. The wire types are therefore
flat and tagged, and the conversions below are the only place that knows both shapes.
"""

from dataclasses import dataclass, field

from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Autonomy, Course, Policy, course_for
from shelf.domain.review import ReviewDepth
from shelf.domain.usage import StepUsage, Usage
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
    proceed_on_deadlock: bool = False
    """Whether a spec or design review that cannot settle lets the work go on; older work has False."""
    spec_review_depth: str = ""
    """How deep the spec review looks, chosen when the work started; empty for work that predates it."""
    design_review_depth: str = ""
    """How deep the design review looks, chosen when the work started; empty for work that predates it."""
    poll_base_seconds: float = 30.0
    poll_ceiling_seconds: float = 900.0
    protocol: int = 1
    """How the work behaves, fixed at start. Work started before the field existed has 1, the original behaviour."""
    context: list[str] = field(default_factory=list[str])
    """Other repositories the agents may read as reference; work started before the field existed has none."""


@dataclass(frozen=True, slots=True)
class StepInput:
    """The input of the activity that runs a step."""

    work: WorkInput
    phase: str
    attempt: int
    feedback: str


@dataclass(frozen=True, slots=True)
class UsageDto:
    """What an agent step used, as the workflow records it."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    turns: int = 0
    seconds: float = 0.0
    models: list[str] = field(default_factory=list[str])


@dataclass(frozen=True, slots=True)
class StepOutput:
    """What a step reports, as a tagged record."""

    kind: str
    verdict: str = ""
    passed: bool = False
    text: str = ""
    waiting: bool = False
    usage: UsageDto | None = None
    """What the agent used; absent for the checks and for a provider that said nothing."""


@dataclass(frozen=True, slots=True)
class StepUsageDto:
    """What one step used and which step it was, as the workflow answers its query."""

    phase: str
    attempt: int
    agent: str
    usage: UsageDto


@dataclass(frozen=True, slots=True)
class AskInput:
    """The input of the activity that announces a wait."""

    work: WorkInput
    phase: str
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class StageInput:
    """The input of the activity that sets the pull request's stage label."""

    work: WorkInput
    phase: str
    reason: str = ""
    """Why a person is awaited, or empty while a step runs."""


@dataclass(frozen=True, slots=True)
class LogEntryDto:
    """One thing that happened at a phase, for the progress comment."""

    phase: str
    text: str
    at: str = ""
    """When it happened (ISO, UTC); empty for entries recorded before times were kept."""


@dataclass(frozen=True, slots=True)
class ProgressInput:
    """The input of the activity that updates the progress comment."""

    work: WorkInput
    log: list[LogEntryDto]
    phase: str
    reason: str = ""
    outcome: str = ""
    updated: str = ""
    """When the work last changed, for the line at the foot of the progress comment."""


@dataclass(frozen=True, slots=True)
class DecisionRecordInput:
    """The input of the activity that records a person's decision in the repository."""

    work: WorkInput
    phase: str
    login: str
    kind: str
    note: str
    at: str


@dataclass(frozen=True, slots=True)
class ClosePullRequestInput:
    """The input of the activity that closes the work's pull request after a person ended the work."""

    work: WorkInput
    reason: str


@dataclass(frozen=True, slots=True)
class ReadyInput:
    """The input of the activity that marks the pull request ready for review or back to draft."""

    work: WorkInput
    ready: bool


@dataclass(frozen=True, slots=True)
class OpenPointsInput:
    """The input of the activity that posts what a review left open."""

    work: WorkInput
    phase: str
    issues: str


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
    updated_at: str = ""
    """When the work last did anything (ISO, UTC); empty for work that predates times."""
    times: dict[str, str] = field(default_factory=dict[str, str])
    """For each phase, when something last happened there."""


def course_of(work: WorkInput) -> Course:
    """The course of the work, from its policy and entry point."""
    policy = Policy(work.max_rounds, work.spec_approval, work.design_review, work.proceed_on_deadlock)
    return course_for(EntryPoint(work.entry), policy, work.protocol)


def context_of(work: WorkInput) -> WorkContext:
    """The context a step runs with."""
    request = WorkRequest(
        RepoRef.parse(work.repo),
        work.requester,
        EntryPoint(work.entry),
        work.text,
        work.pull_request,
        tuple(work.context),
        Autonomy(
            work.spec_approval,
            work.design_review,
            work.proceed_on_deadlock,
            ReviewDepth(work.spec_review_depth) if work.spec_review_depth else None,
            ReviewDepth(work.design_review_depth) if work.design_review_depth else None,
        ),
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
            return Verified(output.passed, output.text, output.waiting)
        case other:
            message = f"unknown step result kind: {other!r}"
            raise ValueError(message)


def output_of(result: StepResult) -> StepOutput:
    """Write a step's report."""
    match result:
        case Produced(usage):
            return StepOutput("produced", usage=usage_dto(usage))
        case Reviewed(verdict, issues, usage):
            return StepOutput("reviewed", verdict=verdict, text=issues, usage=usage_dto(usage))
        case Verified(passed, report, waiting):
            return StepOutput("verified", passed=passed, text=report, waiting=waiting)


def usage_dto(usage: Usage | None) -> UsageDto | None:
    """Write what a step used for the workflow; nothing when the provider said nothing."""
    if usage is None:
        return None
    return UsageDto(
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_tokens,
        usage.cache_write_tokens,
        usage.cost_usd,
        usage.turns,
        usage.seconds,
        list(usage.models),
    )


def usage_of(dto: UsageDto) -> Usage:
    """Read what a step used."""
    return Usage(
        dto.input_tokens,
        dto.output_tokens,
        dto.cache_read_tokens,
        dto.cache_write_tokens,
        dto.cost_usd,
        dto.turns,
        dto.seconds,
        tuple(dto.models),
    )


def step_usages(entries: list[StepUsageDto]) -> tuple[StepUsage, ...]:
    """Read the answer to the usage query."""
    return tuple(StepUsage(e.phase, e.attempt, e.agent, usage_of(e.usage)) for e in entries)


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


def snapshot_of(
    state: State, last_phase: Phase, pull_request_url: str, updated_at: str = "", times: dict[str, str] | None = None
) -> Snapshot:
    """Describe ``state`` for the board; ``last_phase`` is where a finished piece of work ended."""
    seen = dict(times or {})
    match state:
        case Running(phase):
            return Snapshot(phase, pull_request_url=pull_request_url, updated_at=updated_at, times=seen)
        case AwaitingPerson(phase, reason, detail):
            return Snapshot(
                phase,
                waiting_for=reason,
                detail=detail,
                pull_request_url=pull_request_url,
                updated_at=updated_at,
                times=seen,
            )
        case Finished(outcome):
            return Snapshot(
                last_phase, outcome=outcome, pull_request_url=pull_request_url, updated_at=updated_at, times=seen
            )
