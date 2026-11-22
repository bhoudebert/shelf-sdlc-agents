"""How a piece of work is configured to run, and the course that results for an entry point."""

from dataclasses import dataclass, replace
from enum import StrEnum

from shelf.domain.pipeline import FIRST_PHASE, PIPELINE, EntryPoint, Phase
from shelf.domain.review import ReviewDepth


class DeadlockMode(StrEnum):
    """What happens when a reviewer and its author cannot agree (ADR 0021)."""

    ASK = "ask"
    """A person is asked."""
    ARBITRATE_ASK = "arbitrate-ask"
    """An arbitrator decides; a person is asked only when it cannot."""
    ARBITRATE_GO = "arbitrate-go"
    """An arbitrator decides; when it cannot, the work goes on where the phase may be passed."""
    GO = "go"
    """Nobody settles it: the work goes on and the open points are posted (ADR 0013)."""

    @property
    def arbitrates(self) -> bool:
        """Whether an arbitrator is asked first."""
        return self in (DeadlockMode.ARBITRATE_ASK, DeadlockMode.ARBITRATE_GO)

    @property
    def goes_on(self) -> bool:
        """Whether a deadlock that stays unsettled lets the work go on, where the phase may be passed."""
        return self in (DeadlockMode.ARBITRATE_GO, DeadlockMode.GO)


@dataclass(frozen=True, slots=True)
class Policy:
    """The per-repository choices that shape a run."""

    max_rounds: int = 3
    """How many times a loop may send work back before a person is asked."""
    spec_approval: bool = True
    """Whether a person must approve the spec before the design starts."""
    design_review: bool = True
    """Whether a reviewer checks the design before the plan."""
    proceed_on_deadlock: bool = False
    """Whether work goes on, open issues posted, when the spec or design review cannot settle (ADR 0013)."""
    spec_review_depth: ReviewDepth = ReviewDepth.QUICK
    """How hard the spec review looks."""
    design_review_depth: ReviewDepth = ReviewDepth.STANDARD
    """How hard the design review looks."""
    on_deadlock: DeadlockMode | None = None
    """What happens when a reviewer and its author cannot agree; ``None`` reads ``proceed_on_deadlock`` (ADR 0021)."""

    @property
    def deadlock_mode(self) -> DeadlockMode:
        """The answer chosen to a disagreement, else ``go`` when ``proceed_on_deadlock`` is set, else ``ask``."""
        if self.on_deadlock is not None:
            return self.on_deadlock
        return DeadlockMode.GO if self.proceed_on_deadlock else DeadlockMode.ASK

    def removed_stops(self) -> tuple[str, ...]:
        """The stops a person is not asked at, by name: ``spec``, ``design`` and ``deadlock``."""
        return tuple(
            name
            for name, removed in (
                ("spec", not self.spec_approval),
                ("design", not self.design_review),
                ("deadlock", self.deadlock_mode.goes_on),
            )
            if removed
        )

    def __post_init__(self) -> None:
        """Reject a policy that would never allow a loop."""
        if self.max_rounds < 1:
            message = "max_rounds must be at least 1"
            raise ValueError(message)


@dataclass(frozen=True, slots=True)
class Autonomy:
    """How much one piece of work does without a person: what a person chose when starting it."""

    spec_approval: bool
    design_review: bool
    proceed_on_deadlock: bool
    spec_review_depth: ReviewDepth | None = None
    """How deep the spec review looks for this work; ``None`` leaves it to the repository's file."""
    design_review_depth: ReviewDepth | None = None
    """How deep the design review looks for this work; ``None`` leaves it to the repository's file."""
    on_deadlock: DeadlockMode | None = None
    """What happens at a disagreement for this work; ``None`` reads ``proceed_on_deadlock`` (ADR 0021)."""

    @classmethod
    def strictest(cls) -> "Autonomy":
        """The choice that asks a person the most: the approval, the design review, and a wait at every deadlock."""
        return cls(spec_approval=True, design_review=True, proceed_on_deadlock=False)

    @classmethod
    def of(cls, policy: Policy) -> "Autonomy":
        """What a repository's policy says."""
        return cls(
            policy.spec_approval,
            policy.design_review,
            policy.proceed_on_deadlock,
            policy.spec_review_depth,
            policy.design_review_depth,
            policy.on_deadlock,
        )

    def over(self, policy: Policy) -> Policy:
        """``policy`` with these choices in place of its own; the round limit stays the repository's."""
        return replace(
            policy,
            spec_approval=self.spec_approval,
            design_review=self.design_review,
            proceed_on_deadlock=self.proceed_on_deadlock,
            on_deadlock=self.on_deadlock,
            spec_review_depth=self.spec_review_depth or policy.spec_review_depth,
            design_review_depth=self.design_review_depth or policy.design_review_depth,
        )

    @property
    def removes_a_stop(self) -> bool:
        """Whether this asks a person less than the strictest choice does."""
        return (
            not self.spec_approval
            or not self.design_review
            or self.proceed_on_deadlock
            or (self.on_deadlock is not None and self.on_deadlock is not DeadlockMode.ASK)
        )


@dataclass(frozen=True, slots=True)
class Course:
    """The phases one piece of work will go through, and how it ends."""

    phases: tuple[Phase, ...]
    max_rounds: int
    publishes_pull_request: bool
    """False when the work arrived with a pull request of its own."""
    adopts_pull_request: bool = False
    """True when the work changes the branch of a pull request that already exists (protocol 5 and later)."""
    proceeds_on_deadlock: bool = False
    """True when a spec or design review that cannot settle lets the work go on, its open issues posted."""
    deadlock: DeadlockMode = DeadlockMode.ASK
    """What the person who started the work asked for at a disagreement (ADR 0021; read from protocol 13)."""
    protocol: int = 1
    """How this piece of work behaves, fixed when it starts. Work already running keeps the behaviour it started with,
    so a new release never changes what a replayed history does: see ``CURRENT_PROTOCOL``."""

    @property
    def opens_early(self) -> bool:
        """Whether the pull request opens after the first step and is readied at the merge (protocol 2 and later)."""
        return self.protocol >= EARLY_PULL_REQUEST

    @property
    def waits_for_ci(self) -> bool:
        """Whether the checks wait for the repository's CI and look again while it runs (protocol 4 and later)."""
        return self.protocol >= WAITS_FOR_CI

    @property
    def asks_a_person_after_review(self) -> bool:
        """Whether a review of a pull request that is not ours hands its findings to a person, not the implementer."""
        return (
            not self.publishes_pull_request and not self.adopts_pull_request and self.protocol >= REVIEW_ASKS_A_PERSON
        )

    @property
    def review_is_read_only(self) -> bool:
        """Whether this is a review of someone else's pull request that agents never change (protocol 5 and later).

        A person who asks for changes gets another review, since there is no developer to send them to.
        """
        return not self.publishes_pull_request and not self.adopts_pull_request and self.protocol >= READ_ONLY_REVIEW

    @property
    def approval_counts_for_the_gate(self) -> bool:
        """Whether a person who accepts an escalated review has also approved the gate that follows it (protocol 6)."""
        return self.protocol >= ONE_APPROVAL

    @property
    def records_decisions(self) -> bool:
        """Whether a person's decision is written into the repository before the work goes on (protocol 7)."""
        return self.protocol >= RECORDS_DECISIONS

    @property
    def closes_pull_request(self) -> bool:
        """Whether a person who ends the work also closes the pull request it opened (protocol 8)."""
        return self.protocol >= CLOSES_PULL_REQUEST and self.publishes_pull_request

    @property
    def resumes_sessions(self) -> bool:
        """Whether an agent that runs again on the work continues its earlier session (protocol 9)."""
        return self.protocol >= RESUMES_SESSIONS

    @property
    def judges_review_loops(self) -> bool:
        """Whether a review loop ends on a repeated or minor point, not on a count alone (protocol 10)."""
        return self.protocol >= JUDGES_REVIEW_LOOPS

    @property
    def judges_check_loops(self) -> bool:
        """Whether the checks loop ends on a failure that keeps coming back, not on a count alone (protocol 12)."""
        return self.protocol >= JUDGES_CHECK_LOOPS

    @property
    def arbitrates(self) -> bool:
        """Whether a deadlock goes to an arbitrator before a person or the end of the loop (protocol 13)."""
        return self.protocol >= ARBITRATES and self.deadlock.arbitrates

    @property
    def looks_at_ci_before_merge(self) -> bool:
        """Whether the CI is looked at again once the pull request is ready, before a person is asked (protocol 11)."""
        return self.protocol >= LOOKS_AT_CI_BEFORE_MERGE and self.readies_pull_request

    @property
    def readies_pull_request(self) -> bool:
        """Whether the pull request leaves the draft state when the work asks for the merge: ours, or adopted."""
        return self.opens_early and (self.publishes_pull_request or self.adopts_pull_request)


CURRENT_PROTOCOL = 13
"""The behaviour new work starts with. Raise it, and gate the new behaviour on it, whenever a change would alter what
the workflow does for a history recorded before: protocol 1 is the original behaviour, which old work keeps."""

EARLY_PULL_REQUEST = 2
"""The protocol that opens the pull request after the first step, labels its stage, readies it at the merge and keeps
a progress comment."""

REVIEW_ASKS_A_PERSON = 3
"""The protocol under which a review of someone else's pull request that finds problems waits for a person instead of
sending the work back to the implementer."""


WAITS_FOR_CI = 4
"""The protocol under which the checks also read the repository's CI on the pull request, wait for it to finish, and
send red runs back to the implementer."""


READ_ONLY_REVIEW = 5
"""The protocol from which a read-only review answers a request for changes with another review, and from which an
existing pull request can be adopted."""

ONE_APPROVAL = 6
"""The protocol under which accepting an escalated review also approves the gate right after it, so that a person is
not asked twice for the same decision."""


RECORDS_DECISIONS = 7
"""The protocol under which every decision a person makes is recorded in the work's decision log in the repository."""


CLOSES_PULL_REQUEST = 8
"""The protocol under which a person who rejects or aborts the work also closes the pull request the work opened."""


RESUMES_SESSIONS = 9
"""The protocol under which an agent sent back continues its own session instead of starting a new one."""

JUDGES_REVIEW_LOOPS = 10
"""The protocol under which a reviewer's repeated or minor points decide how a review loop ends."""

LOOKS_AT_CI_BEFORE_MERGE = 11
"""The protocol under which the work looks at the CI after the pull request is ready, before it asks for the merge."""


JUDGES_CHECK_LOOPS = 12
"""The protocol under which a failing check goes back to the implementer while the failure changes, and a person is
asked when the same one comes back three times in a row, or at ten times the maximum number of rounds."""


ARBITRATES = 13
"""The protocol under which a deadlock goes to an arbitrator first, when the work asks for one (ADR 0021)."""


def course_for(entry: EntryPoint, policy: Policy, protocol: int = CURRENT_PROTOCOL) -> Course:
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
        publishes_pull_request=entry not in (EntryPoint.PULL_REQUEST_REVIEW, EntryPoint.PULL_REQUEST_WORK),
        adopts_pull_request=entry is EntryPoint.PULL_REQUEST_WORK,
        proceeds_on_deadlock=policy.deadlock_mode.goes_on,
        deadlock=policy.deadlock_mode,
        protocol=protocol,
    )
