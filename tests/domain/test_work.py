from collections.abc import Callable

from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.pipeline import KIND, EntryPoint, Kind, Phase
from shelf.domain.policy import CURRENT_PROTOCOL, Course, Policy, course_for
from shelf.domain.work import (
    WAITING_FOR_CI,
    AskPerson,
    AwaitingPerson,
    CancelStep,
    Command,
    Conclude,
    DecisionKind,
    Event,
    Finished,
    NoteOpenPoints,
    Outcome,
    PersonDecided,
    Produced,
    PublishPullRequest,
    PullRequestClosed,
    Reason,
    Reviewed,
    Running,
    RunStep,
    SetPullRequestReady,
    State,
    StepDone,
    StepFailed,
    Verdict,
    Verified,
    decide,
    start,
)

PERSON = "alice"


def approve(phase: Phase) -> Event:
    """The event that lets ``phase`` succeed."""
    match KIND[phase]:
        case Kind.REVIEW:
            return StepDone(Reviewed(Verdict.APPROVE))
        case Kind.VERIFY:
            return StepDone(Verified(passed=True))
        case _:
            return StepDone(Produced())


def drive(course: Course, answer: Callable[[State], Event | None]) -> tuple[list[Command], State]:
    """Run the machine, asking ``answer`` for the next event until it has none or the work ends."""
    state, commands = start(course)
    log = list(commands)
    while (event := answer(state)) is not None:
        state, more = decide(course, state, event)
        log.extend(more)
    return log, state


def happy(state: State) -> Event | None:
    match state:
        case Running(phase):
            return approve(phase)
        case AwaitingPerson(reason=Reason.GATE):
            return PersonDecided(PERSON, DecisionKind.APPROVE)
        case AwaitingPerson(reason=Reason.MERGE):
            return PullRequestClosed(merged=True)
        case _:
            return None


def phases_run(log: list[Command]) -> list[Phase]:
    return [c.phase for c in log if isinstance(c, RunStep)]


def test_work_started_from_a_need_goes_through_every_step_then_waits_for_the_merge() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    log, state = drive(course, happy)
    assert phases_run(log) == [
        Phase.INTAKE,
        Phase.SPEC_REVIEW,
        Phase.DESIGN,
        Phase.DESIGN_REVIEW,
        Phase.PLAN,
        Phase.IMPLEMENT,
        Phase.VERIFY,
        Phase.CODE_REVIEW,
    ]
    assert state == Finished(Outcome.MERGED)
    assert PublishPullRequest() in log
    assert log[-1] == Conclude(Outcome.MERGED)


def test_a_pull_request_review_starts_at_code_review_and_publishes_nothing() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy())
    log, _ = drive(course, happy)
    assert phases_run(log) == [Phase.CODE_REVIEW]
    assert PublishPullRequest() not in log


def test_a_review_of_someone_elses_pull_request_that_finds_problems_asks_a_person() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy())
    state, commands = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.CHANGES, "rename it")))
    assert state == AwaitingPerson(Phase.CODE_REVIEW, Reason.ESCALATION, "rename it")
    assert commands == (AskPerson(Phase.CODE_REVIEW, Reason.ESCALATION, "rename it"),)


def test_work_started_before_protocol_5_hands_the_findings_of_a_review_to_the_implementer_on_request() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy(), protocol=4)
    waiting = AwaitingPerson(Phase.CODE_REVIEW, Reason.ESCALATION, "rename it")
    state, commands = decide(course, waiting, PersonDecided("bob", DecisionKind.CHANGES))
    assert state == Running(Phase.IMPLEMENT, 0, "rename it")
    assert commands == (RunStep(Phase.IMPLEMENT, 0, "rename it"),)


def test_work_started_before_the_change_still_sends_the_review_back_to_the_implementer() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy(), protocol=2)
    state, _ = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.CHANGES, "rename it")))
    assert state == Running(Phase.IMPLEMENT, 1, "rename it")


def test_our_own_work_still_loops_back_automatically() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy())
    state, _ = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.CHANGES, "rename it")))
    assert state == Running(Phase.IMPLEMENT, 1, "rename it")


def test_the_spec_gate_waits_for_a_person() -> None:
    course = course_for(EntryPoint.SPEC, Policy())
    state, _ = start(course)
    state, _ = decide(course, state, approve(Phase.SPEC_REVIEW))
    assert state == AwaitingPerson(Phase.SPEC_APPROVAL, Reason.GATE)


def test_changes_requested_at_a_gate_send_the_work_back_with_the_note() -> None:
    course = course_for(EntryPoint.SPEC, Policy())
    state, _ = decide(
        course,
        AwaitingPerson(Phase.SPEC_APPROVAL, Reason.GATE),
        PersonDecided(PERSON, DecisionKind.CHANGES, "add limits"),
    )
    assert state == Running(Phase.INTAKE, 0, "add limits")


def test_a_reviewer_asking_for_changes_sends_work_back_with_the_issues() -> None:
    course = course_for(EntryPoint.SPEC, Policy())
    state, commands = decide(course, Running(Phase.SPEC_REVIEW), StepDone(Reviewed(Verdict.CHANGES, "too vague")))
    assert state == Running(Phase.INTAKE, 1, "too vague")
    assert commands == (PublishPullRequest(), RunStep(Phase.INTAKE, 1, "too vague"))


def test_the_loop_gives_up_after_the_policy_limit_and_asks_a_person() -> None:
    course = course_for(EntryPoint.SPEC, Policy(max_rounds=2))
    reject = StepDone(Reviewed(Verdict.CHANGES, "still wrong"))

    def answer(state: State) -> Event | None:
        return (
            reject
            if isinstance(state, Running) and state.phase is Phase.SPEC_REVIEW
            else (approve(state.phase) if isinstance(state, Running) else None)
        )

    _, state = drive(course, answer)
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION
    assert "limit of 2 rounds" in state.detail


def test_failing_checks_send_work_back_to_the_implementer_with_the_report() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy())
    state, _ = decide(course, Running(Phase.VERIFY), StepDone(Verified(passed=False, report="2 tests fail")))
    assert state == Running(Phase.IMPLEMENT, 1, "2 tests fail")


def test_the_round_budget_survives_the_trip_through_the_checks() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy(max_rounds=1))
    state, _ = decide(course, Running(Phase.IMPLEMENT, 1), approve(Phase.IMPLEMENT))
    state, _ = decide(course, state, approve(Phase.VERIFY))
    assert state == Running(Phase.CODE_REVIEW, 1)
    state, _ = decide(course, state, StepDone(Reviewed(Verdict.CHANGES, "again")))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION


def test_a_failed_step_asks_a_person_who_can_resume_it() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, _ = decide(course, Running(Phase.DESIGN), StepFailed("model unavailable"))
    assert state == AwaitingPerson(Phase.DESIGN, Reason.FAILURE, "model unavailable")
    state, commands = decide(course, state, PersonDecided(PERSON, DecisionKind.RESUME, "try again"))
    assert state == Running(Phase.DESIGN, 0, "try again")
    assert commands == (RunStep(Phase.DESIGN, 0, "try again"),)


def test_a_person_can_accept_an_escalated_review_as_it_is() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, _ = decide(
        course,
        AwaitingPerson(Phase.DESIGN_REVIEW, Reason.ESCALATION, "unsure"),
        PersonDecided(PERSON, DecisionKind.APPROVE),
    )
    assert state == Running(Phase.PLAN)


def test_accepting_an_escalated_spec_review_also_approves_the_spec() -> None:
    escalated = AwaitingPerson(Phase.SPEC_REVIEW, Reason.ESCALATION, "unsure")
    state, commands = decide(
        course_for(EntryPoint.NEED, Policy()), escalated, PersonDecided(PERSON, DecisionKind.APPROVE)
    )
    assert state == Running(Phase.DESIGN)
    assert commands == (RunStep(Phase.DESIGN, 0, ""),)


def test_work_on_an_earlier_protocol_still_asks_twice() -> None:
    escalated = AwaitingPerson(Phase.SPEC_REVIEW, Reason.ESCALATION, "unsure")
    state, _ = decide(
        course_for(EntryPoint.NEED, Policy(), protocol=5), escalated, PersonDecided(PERSON, DecisionKind.APPROVE)
    )
    assert state == AwaitingPerson(Phase.SPEC_APPROVAL, Reason.GATE, "")


def test_a_failure_cannot_be_approved_away() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    waiting = AwaitingPerson(Phase.IMPLEMENT, Reason.FAILURE, "boom")
    assert decide(course, waiting, PersonDecided(PERSON, DecisionKind.APPROVE)) == (waiting, ())


def test_aborting_a_running_step_cancels_it_and_ends_the_work() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, commands = decide(course, Running(Phase.IMPLEMENT), PersonDecided(PERSON, DecisionKind.ABORT))
    assert state == Finished(Outcome.ABORTED)
    assert commands == (CancelStep(Phase.IMPLEMENT), Conclude(Outcome.ABORTED))


def test_changes_requested_on_the_pull_request_send_the_work_back_to_the_implementer() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    waiting = AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE)
    state, _ = decide(course, waiting, PersonDecided(PERSON, DecisionKind.CHANGES, "rename it"))
    assert state == Running(Phase.IMPLEMENT, 0, "rename it")


def test_a_closed_pull_request_ends_the_work_without_a_merge() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, commands = decide(course, AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE), PullRequestClosed(merged=False))
    assert state == Finished(Outcome.CLOSED)
    assert commands == (Conclude(Outcome.CLOSED),)


def test_a_result_of_the_wrong_kind_asks_a_person_instead_of_crashing() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, _ = decide(course, Running(Phase.DESIGN), StepDone(Verified(passed=True)))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.FAILURE


# Properties over any sequence of events.

events = st.one_of(
    st.builds(StepDone, st.builds(Produced)),
    st.builds(StepDone, st.builds(Reviewed, st.sampled_from(Verdict), st.text(max_size=5))),
    st.builds(StepDone, st.builds(Verified, st.booleans(), st.text(max_size=5))),
    st.builds(StepFailed, st.text(max_size=5)),
    st.builds(PersonDecided, st.just(PERSON), st.sampled_from(DecisionKind), st.text(max_size=5)),
    st.builds(PullRequestClosed, st.booleans()),
)
entries = st.sampled_from(EntryPoint)
policies = st.builds(
    Policy,
    max_rounds=st.integers(1, 4),
    spec_approval=st.booleans(),
    design_review=st.booleans(),
)


@given(entries, policies, st.lists(events, max_size=60))
def test_a_finished_piece_of_work_never_comes_back(entry: EntryPoint, policy: Policy, sequence: list[Event]) -> None:
    course = course_for(entry, policy)
    state, _ = start(course)
    for event in sequence:
        was_finished = isinstance(state, Finished)
        before = state
        state, commands = decide(course, state, event)
        if was_finished:
            assert (state, commands) == (before, ())


@given(entries, policies, st.lists(events, max_size=60))
def test_the_state_always_matches_the_commands(entry: EntryPoint, policy: Policy, sequence: list[Event]) -> None:
    course = course_for(entry, policy)
    state, commands = start(course)
    for event in [None, *sequence]:
        if event is not None:
            state, commands = decide(course, state, event)
        match state:
            case Running(phase, attempt, feedback):
                assert commands[-1:] in ((), (RunStep(phase, attempt, feedback),))
                assert set(commands[:-1]) <= {PublishPullRequest()}
                assert attempt <= policy.max_rounds
            case AwaitingPerson():
                assert commands == () or isinstance(commands[-1], AskPerson)
            case Finished(outcome):
                assert Conclude(outcome) in commands or commands == ()


@given(entries, policies, st.lists(events, max_size=80))
def test_the_work_is_only_ever_asked_for_phases_of_its_course_or_a_loop_back_target(
    entry: EntryPoint, policy: Policy, sequence: list[Event]
) -> None:
    course = course_for(entry, policy)
    state, commands = start(course)
    allowed = set(course.phases) | {Phase.INTAKE, Phase.DESIGN, Phase.IMPLEMENT}
    for event in sequence:
        state, commands = decide(course, state, event)
        assert all(c.phase in allowed for c in commands if isinstance(c, RunStep))


def test_changes_asked_where_a_phase_has_no_loop_back_redo_that_phase() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    waiting = AwaitingPerson(Phase.DESIGN, Reason.FAILURE, "boom")
    state, _ = decide(course, waiting, PersonDecided(PERSON, DecisionKind.CHANGES, "use the new API"))
    assert state == Running(Phase.DESIGN, 0, "use the new API")


def test_the_pull_request_opens_as_soon_as_the_first_step_is_done() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    state, commands = decide(course, Running(Phase.INTAKE), StepDone(Produced()))
    assert commands[0] == PublishPullRequest()
    assert state == Running(Phase.SPEC_REVIEW)


def test_a_pull_request_that_already_exists_is_never_published() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy())
    _, commands = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.APPROVE)))
    assert PublishPullRequest() not in commands
    assert SetPullRequestReady(ready=True) not in commands


def test_later_steps_do_not_ask_for_the_pull_request_again() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    _, commands = decide(course, Running(Phase.SPEC_REVIEW), StepDone(Reviewed(Verdict.APPROVE)))
    assert PublishPullRequest() not in commands


def test_the_pull_request_is_marked_ready_when_the_reviewed_work_reaches_the_merge() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy())
    state, commands = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.APPROVE)))
    assert state == AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE)
    assert SetPullRequestReady(ready=True) in commands
    assert commands.index(SetPullRequestReady(ready=True)) < commands.index(
        AskPerson(Phase.PULL_REQUEST, Reason.MERGE, "")
    )


def test_changes_asked_on_the_pull_request_put_it_back_to_draft() -> None:
    course = course_for(EntryPoint.NEED, Policy())
    waiting = AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE)
    _, commands = decide(course, waiting, PersonDecided(PERSON, DecisionKind.CHANGES, "rename it"))
    assert commands[0] == SetPullRequestReady(ready=False)
    assert RunStep(Phase.IMPLEMENT, 0, "rename it") in commands


def test_work_started_before_the_early_pull_request_keeps_its_original_behaviour() -> None:
    course = course_for(EntryPoint.NEED, Policy(), protocol=1)
    _, first = decide(course, Running(Phase.INTAKE), StepDone(Produced()))
    assert PublishPullRequest() not in first
    _, merge = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.APPROVE)))
    assert PublishPullRequest() in merge  # the original: published at the merge
    assert SetPullRequestReady(ready=True) not in merge
    _, back = decide(
        course, AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE), PersonDecided(PERSON, DecisionKind.CHANGES)
    )
    assert SetPullRequestReady(ready=False) not in back


def test_new_work_starts_with_the_current_protocol() -> None:
    assert course_for(EntryPoint.NEED, Policy()).protocol == CURRENT_PROTOCOL
    assert course_for(EntryPoint.NEED, Policy()).opens_early


def test_the_checks_that_find_the_ci_still_running_look_again_in_the_same_round() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy())
    state, commands = decide(course, Running(Phase.VERIFY, 1), StepDone(Verified(False, "slow", waiting=True)))
    assert state == Running(Phase.VERIFY, 1, WAITING_FOR_CI)
    assert commands == (RunStep(Phase.VERIFY, 1, WAITING_FOR_CI),)


def test_red_ci_sends_the_work_back_to_the_implementer_like_failing_checks() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy())
    state, _ = decide(course, Running(Phase.VERIFY, 0, WAITING_FOR_CI), StepDone(Verified(False, "CI is red")))
    assert state == Running(Phase.IMPLEMENT, 1, "CI is red")


def test_work_started_before_the_ci_was_read_does_not_wait_for_it() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy(), protocol=3)
    state, _ = decide(course, Running(Phase.VERIFY, 0), StepDone(Verified(False, "", waiting=True)))
    assert state == Running(Phase.CODE_REVIEW, 0)


def test_asking_for_changes_after_a_read_only_review_asks_for_another_review_not_for_a_developer() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy())
    waiting = AwaitingPerson(Phase.CODE_REVIEW, Reason.ESCALATION, "rename it")
    state, commands = decide(course, waiting, PersonDecided("bob", DecisionKind.CHANGES, "also look at the tests"))
    assert state == Running(Phase.CODE_REVIEW, 0, "also look at the tests")
    assert commands == (RunStep(Phase.CODE_REVIEW, 0, "also look at the tests"),)


def test_work_on_a_pull_request_goes_from_the_developer_through_the_checks_and_the_review_to_the_merge() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_WORK, Policy())
    assert course.phases == (Phase.IMPLEMENT, Phase.VERIFY, Phase.CODE_REVIEW, Phase.PULL_REQUEST)
    assert course.adopts_pull_request
    assert not course.publishes_pull_request


def test_work_on_a_pull_request_never_opens_a_pull_request_but_readies_the_one_it_has_at_the_merge() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_WORK, Policy())
    log, _ = drive(course, happy)
    assert PublishPullRequest() not in log
    assert SetPullRequestReady(ready=True) in log


def test_a_review_of_work_on_a_pull_request_sends_changes_back_to_the_developer_by_itself() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_WORK, Policy())
    state, _ = decide(course, Running(Phase.CODE_REVIEW), StepDone(Reviewed(Verdict.CHANGES, "rename it")))
    assert state == Running(Phase.IMPLEMENT, 1, "rename it")


def test_changes_asked_at_the_merge_of_work_on_a_pull_request_put_it_back_to_draft() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_WORK, Policy())
    waiting = AwaitingPerson(Phase.PULL_REQUEST, Reason.MERGE)
    state, commands = decide(course, waiting, PersonDecided("bob", DecisionKind.CHANGES, "one more thing"))
    assert state == Running(Phase.IMPLEMENT, 0, "one more thing")
    assert commands[0] == SetPullRequestReady(ready=False)


def test_work_started_before_protocol_5_has_no_adopted_pull_request_behaviour() -> None:
    course = course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy(), protocol=4)
    assert not course.review_is_read_only
    assert not course.adopts_pull_request


def deadlocked(phase: Phase, verdict: Verdict = Verdict.CHANGES) -> Callable[[State], Event | None]:
    """Everything is approved, except that ``phase`` never agrees."""

    def answer(state: State) -> Event | None:
        if isinstance(state, Running) and state.phase is phase:
            return StepDone(Reviewed(verdict, f"{phase} still disagrees"))
        return happy(state)

    return answer


def test_a_deadlocked_spec_review_goes_on_when_the_policy_says_so_and_notes_what_stayed_open() -> None:
    course = course_for(EntryPoint.SPEC, Policy(max_rounds=1, spec_approval=False, proceed_on_deadlock=True))
    log, state = drive(course, deadlocked(Phase.SPEC_REVIEW))
    notes = [c for c in log if isinstance(c, NoteOpenPoints)]
    assert [n.phase for n in notes] == [Phase.SPEC_REVIEW]
    assert "limit of 1 rounds" in notes[0].issues
    assert Phase.DESIGN in phases_run(log)
    assert state == Finished(Outcome.MERGED)


def test_a_design_review_that_cannot_decide_goes_on_to_the_plan() -> None:
    course = course_for(EntryPoint.DESIGN, Policy(proceed_on_deadlock=True))
    log, _ = drive(course, deadlocked(Phase.DESIGN_REVIEW, Verdict.ESCALATE))
    assert [c.phase for c in log if isinstance(c, NoteOpenPoints)] == [Phase.DESIGN_REVIEW]
    assert Phase.PLAN in phases_run(log)


def test_the_spec_approval_still_asks_when_it_is_on_after_a_passed_deadlock() -> None:
    course = course_for(EntryPoint.SPEC, Policy(max_rounds=1, proceed_on_deadlock=True))
    _, state = drive(course, lambda s: deadlocked(Phase.SPEC_REVIEW)(s) if isinstance(s, Running) else None)
    assert state == AwaitingPerson(Phase.SPEC_APPROVAL, Reason.GATE)


def test_work_that_does_not_proceed_still_waits_at_a_deadlock_and_notes_nothing() -> None:
    course = course_for(EntryPoint.SPEC, Policy(max_rounds=1))
    log, state = drive(course, deadlocked(Phase.SPEC_REVIEW))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION
    assert not [c for c in log if isinstance(c, NoteOpenPoints)]


def test_failing_checks_and_a_code_review_that_cannot_decide_still_wait_for_a_person() -> None:
    course = course_for(EntryPoint.IMPLEMENT, Policy(max_rounds=1, proceed_on_deadlock=True))

    def red(state: State) -> Event | None:
        if isinstance(state, Running) and state.phase is Phase.VERIFY:
            return StepDone(Verified(passed=False, report="make test failed"))
        return happy(state)

    _, state = drive(course, red)
    assert state == AwaitingPerson(Phase.VERIFY, Reason.ESCALATION, "limit of 1 rounds reached:\nmake test failed")
    _, state = drive(course, deadlocked(Phase.CODE_REVIEW, Verdict.ESCALATE))
    assert isinstance(state, AwaitingPerson)
    assert (state.phase, state.reason) == (Phase.CODE_REVIEW, Reason.ESCALATION)


@given(
    st.lists(st.sampled_from([Verdict.APPROVE, Verdict.CHANGES, Verdict.ESCALATE]), max_size=12),
    st.integers(min_value=1, max_value=4),
)
def test_a_work_that_proceeds_never_waits_at_a_review_of_a_document(verdicts: list[Verdict], rounds: int) -> None:
    course = course_for(EntryPoint.NEED, Policy(max_rounds=rounds, spec_approval=False, proceed_on_deadlock=True))
    remaining = iter(verdicts)

    def answer(state: State) -> Event | None:
        if isinstance(state, Running) and state.phase in (Phase.SPEC_REVIEW, Phase.DESIGN_REVIEW):
            return StepDone(Reviewed(next(remaining, Verdict.CHANGES), "open"))
        return happy(state)

    _, state = drive(course, answer)
    assert state == Finished(Outcome.MERGED)
