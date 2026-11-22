import pytest

from shelf.domain.config import RepoConfig
from shelf.domain.pipeline import PIPELINE, EntryPoint, Phase
from shelf.domain.policy import Autonomy, DeadlockMode, Policy, course_for
from shelf.domain.review import ReviewDepth


def test_the_default_course_from_a_need_is_the_whole_pipeline() -> None:
    assert course_for(EntryPoint.NEED, Policy()).phases == PIPELINE


def test_turning_off_the_gate_and_the_design_review_removes_those_phases() -> None:
    course = course_for(EntryPoint.NEED, Policy(spec_approval=False, design_review=False))
    assert Phase.SPEC_APPROVAL not in course.phases
    assert Phase.DESIGN_REVIEW not in course.phases


def test_only_work_that_arrives_without_a_pull_request_publishes_one() -> None:
    assert course_for(EntryPoint.PLAN, Policy()).publishes_pull_request
    assert not course_for(EntryPoint.PULL_REQUEST_REVIEW, Policy()).publishes_pull_request


def test_a_policy_must_allow_at_least_one_round() -> None:
    with pytest.raises(ValueError, match="max_rounds"):
        Policy(max_rounds=0)


def test_only_the_current_protocol_waits_for_the_repositorys_ci() -> None:
    assert not course_for(EntryPoint.IMPLEMENT, Policy(), protocol=3).waits_for_ci
    assert course_for(EntryPoint.IMPLEMENT, Policy(), protocol=4).waits_for_ci


def test_work_waits_at_a_deadlock_unless_the_policy_says_otherwise() -> None:
    assert not course_for(EntryPoint.NEED, Policy()).proceeds_on_deadlock
    assert course_for(EntryPoint.NEED, Policy(proceed_on_deadlock=True)).proceeds_on_deadlock


def test_the_choices_of_a_person_replace_the_three_of_the_repository_and_keep_its_round_limit() -> None:
    repository = Policy(max_rounds=5, spec_approval=True, design_review=True)
    chosen = Autonomy(spec_approval=False, design_review=True, proceed_on_deadlock=True).over(repository)
    assert chosen == Policy(max_rounds=5, spec_approval=False, design_review=True, proceed_on_deadlock=True)


def test_the_choices_start_from_what_the_repository_says() -> None:
    assert Autonomy.of(Policy(design_review=False)) == Autonomy(
        True, False, False, ReviewDepth.QUICK, ReviewDepth.STANDARD
    )
    assert Autonomy.strictest() == Autonomy(True, True, False, on_deadlock=DeadlockMode.ASK)


def test_only_the_strictest_choice_removes_no_stop() -> None:
    assert not Autonomy.strictest().removes_a_stop
    assert Autonomy(False, True, False).removes_a_stop
    assert Autonomy(True, False, False).removes_a_stop
    assert Autonomy(True, True, True).removes_a_stop


def test_the_stops_a_policy_removes_are_named_in_a_fixed_order() -> None:
    assert Policy().removed_stops() == ()
    assert Policy(design_review=False, spec_approval=False).removed_stops() == ("spec", "design")
    assert Policy(proceed_on_deadlock=True).removed_stops() == ("deadlock",)


def test_a_depth_chosen_for_one_work_replaces_the_repositorys_and_silence_keeps_it() -> None:
    repository = Policy(spec_review_depth=ReviewDepth.QUICK, design_review_depth=ReviewDepth.STANDARD)
    chosen = Autonomy(True, True, False, design_review_depth=ReviewDepth.THOROUGH).over(repository)
    assert chosen.design_review_depth is ReviewDepth.THOROUGH
    assert chosen.spec_review_depth is ReviewDepth.QUICK
    assert Autonomy(True, True, False).over(repository).design_review_depth is ReviewDepth.STANDARD


def test_new_work_continues_its_agents_sessions_and_work_from_before_does_not() -> None:

    assert course_for(EntryPoint.NEED, Policy()).resumes_sessions
    assert not course_for(EntryPoint.NEED, Policy(), 8).resumes_sessions


def test_a_repository_that_says_nothing_gets_the_autonomous_flow() -> None:
    policy = Policy.autonomous()
    assert (policy.spec_approval, policy.design_review) == (False, True)
    assert policy.deadlock_mode is DeadlockMode.ARBITRATE_GO
    assert RepoConfig().policy == policy
    assert policy.removed_stops() == ("spec", "deadlock")


def test_the_strict_policy_is_still_what_a_bare_policy_says() -> None:
    assert Policy().deadlock_mode is DeadlockMode.ASK
    assert Policy().spec_approval
