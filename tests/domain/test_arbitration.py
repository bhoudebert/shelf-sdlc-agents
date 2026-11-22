from shelf.domain.pipeline import KIND, EntryPoint, Kind, Phase
from shelf.domain.policy import ARBITRATES, Autonomy, Course, DeadlockMode, Policy, course_for
from shelf.domain.work import (
    Arbitrate,
    Arbitrated,
    Arbitrating,
    ArbitrationVerdict,
    AskPerson,
    AwaitingPerson,
    DecisionKind,
    Finished,
    NoteOpenPoints,
    Outcome,
    PersonDecided,
    Produced,
    Reason,
    RecordArbitration,
    Reviewed,
    Running,
    RunStep,
    StepDone,
    StepFailed,
    StepResult,
    Transition,
    Verdict,
    Verified,
    decide,
    start,
)


def _course(mode: DeadlockMode, entry: EntryPoint = EntryPoint.SPEC, *, spec_approval: bool = True) -> Course:
    return course_for(entry, Policy(spec_approval=spec_approval, on_deadlock=mode), protocol=ARBITRATES)


def _deadlock(course: Course, phase: Phase = Phase.SPEC_REVIEW) -> Transition:
    """Bring the work to a deadlock of ``phase`` by a reviewer's ESCALATE and return what follows."""
    state, _ = start(course)
    while not (isinstance(state, Running) and state.phase is phase):
        match state:
            case Running(p):
                state, _ = decide(course, state, StepDone(_ok(p)))
            case AwaitingPerson(reason=Reason.GATE):
                state, _ = decide(course, state, PersonDecided("a", DecisionKind.APPROVE))
            case _:
                msg = f"never reached {phase}: {state}"
                raise AssertionError(msg)
    return decide(course, state, StepDone(Reviewed(Verdict.ESCALATE, "the reviewer cannot decide")))


def _ok(phase: Phase) -> StepResult:
    match KIND[phase]:
        case Kind.REVIEW:
            return Reviewed(Verdict.APPROVE)
        case Kind.VERIFY:
            return Verified(passed=True)
        case _:
            return Produced()


def test_the_answers_are_read_from_the_old_setting_when_none_is_chosen() -> None:
    assert Policy().deadlock_mode is DeadlockMode.ASK
    assert Policy(proceed_on_deadlock=True).deadlock_mode is DeadlockMode.GO
    assert Policy(proceed_on_deadlock=True, on_deadlock=DeadlockMode.ARBITRATE_ASK).deadlock_mode is (
        DeadlockMode.ARBITRATE_ASK
    )
    assert Autonomy.of(Policy(on_deadlock=DeadlockMode.ARBITRATE_GO)).on_deadlock is DeadlockMode.ARBITRATE_GO


def test_a_work_that_asks_an_arbitrator_removes_the_deadlock_stop_only_when_it_goes_on() -> None:
    assert "deadlock" not in Policy(on_deadlock=DeadlockMode.ARBITRATE_ASK).removed_stops()
    assert "deadlock" in Policy(on_deadlock=DeadlockMode.ARBITRATE_GO).removed_stops()
    assert "deadlock" in Policy(on_deadlock=DeadlockMode.GO).removed_stops()


def test_an_arbitrating_answer_removes_a_stop_for_the_start_form() -> None:
    assert Autonomy(True, True, False, on_deadlock=DeadlockMode.ARBITRATE_ASK).removes_a_stop
    assert not Autonomy(True, True, False, on_deadlock=DeadlockMode.ASK).removes_a_stop


def test_a_deadlock_goes_to_the_arbitrator_first() -> None:
    state, commands = _deadlock(_course(DeadlockMode.ARBITRATE_ASK))
    assert isinstance(state, Arbitrating)
    assert commands[-1] == Arbitrate(Phase.SPEC_REVIEW, "the reviewer cannot decide")


def test_an_earlier_protocol_does_not_arbitrate() -> None:
    course = course_for(EntryPoint.SPEC, Policy(on_deadlock=DeadlockMode.ARBITRATE_ASK), protocol=ARBITRATES - 1)
    state, commands = _deadlock(course)
    assert isinstance(state, AwaitingPerson)
    assert isinstance(commands[-1], AskPerson)


def test_a_fix_sends_the_author_back_with_the_instructions_and_records_the_arbitration() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, commands = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.FIX, "1. change line 17")))
    assert isinstance(state, Running)
    assert state.phase is Phase.INTAKE
    assert state.feedback.endswith("1. change line 17")
    assert "run each proof it names" in state.feedback.lower()
    assert state.arbitrated == (Phase.SPEC_REVIEW,)
    assert commands[0] == RecordArbitration(Phase.SPEC_REVIEW, ArbitrationVerdict.FIX, "1. change line 17")
    assert isinstance(commands[-1], RunStep)


def test_the_same_deadlock_is_not_arbitrated_twice() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, _ = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.FIX, "fix it")))
    state, _ = decide(course, state, StepDone(_ok(Phase.INTAKE)))
    assert isinstance(state, Running)
    assert state.phase is Phase.SPEC_REVIEW
    assert state.arbitrated == (Phase.SPEC_REVIEW,)
    state, commands = decide(course, state, StepDone(Reviewed(Verdict.ESCALATE, "still not settled")))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION
    assert not any(isinstance(c, Arbitrate) for c in commands)


def test_an_overrule_goes_on_to_the_next_phase_and_is_recorded() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, commands = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.OVERRULE, "no evidence")))
    assert isinstance(state, AwaitingPerson)  # the spec approval gate is next
    assert state.reason is Reason.GATE
    assert commands[0] == RecordArbitration(Phase.SPEC_REVIEW, ArbitrationVerdict.OVERRULE, "no evidence")


def test_an_escalation_asks_a_person_with_the_brief_when_the_answer_is_arbitrate_ask() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, commands = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.ESCALATE, "choose A or B")))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION
    assert state.detail.startswith("choose A or B")
    assert "the reviewer cannot decide" in state.detail
    assert isinstance(commands[0], RecordArbitration)
    assert isinstance(commands[-1], AskPerson)


def test_an_escalation_goes_on_in_a_document_review_when_the_answer_is_arbitrate_go() -> None:
    course = _course(DeadlockMode.ARBITRATE_GO, spec_approval=False)
    state, _ = _deadlock(course)
    state, commands = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.ESCALATE, "choose A or B")))
    assert isinstance(state, Running)
    assert state.phase is Phase.DESIGN
    [note] = [c for c in commands if isinstance(c, NoteOpenPoints)]
    assert "choose A or B" in note.issues


def test_an_escalation_in_a_code_review_asks_a_person_even_when_the_answer_goes_on() -> None:
    course = _course(DeadlockMode.ARBITRATE_GO, EntryPoint.IMPLEMENT)
    state, _ = _deadlock(course, Phase.CODE_REVIEW)
    state, _ = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.ESCALATE, "a person must choose")))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION


def test_a_failing_check_is_never_overruled() -> None:
    course = _course(DeadlockMode.ARBITRATE_GO, EntryPoint.IMPLEMENT)
    state, _ = start(course)
    state, _ = decide(course, state, StepDone(_ok(Phase.IMPLEMENT)))
    for _ in range(3):  # the same failure comes back until the checks loop gives up
        assert isinstance(state, Running)
        assert state.phase is Phase.VERIFY
        state, _ = decide(course, state, StepDone(Verified(passed=False, report="boom 12")))
        if isinstance(state, Arbitrating):
            break
        state, _ = decide(course, state, StepDone(_ok(Phase.IMPLEMENT)))
    assert isinstance(state, Arbitrating)
    state, _ = decide(course, state, StepDone(Arbitrated(ArbitrationVerdict.OVERRULE, "ignore it")))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION


def test_an_arbitrator_that_fails_leaves_the_deadlock_to_the_answer() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, commands = decide(course, state, StepFailed("the model is unreachable"))
    assert isinstance(state, AwaitingPerson)
    assert state.reason is Reason.ESCALATION
    assert isinstance(commands[-1], AskPerson)


def test_a_person_can_end_the_work_while_the_arbitrator_reads() -> None:
    course = _course(DeadlockMode.ARBITRATE_ASK)
    state, _ = _deadlock(course)
    state, _ = decide(course, state, PersonDecided("a", DecisionKind.ABORT))
    assert state == Finished(Outcome.ABORTED)
