import pytest

from shelf.domain.pipeline import PIPELINE, EntryPoint, Phase
from shelf.domain.policy import Autonomy, Policy, course_for


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
    assert Autonomy.of(Policy(design_review=False)) == Autonomy(True, False, False)
    assert Autonomy.strictest() == Autonomy(True, True, False)


def test_only_the_strictest_choice_removes_no_stop() -> None:
    assert not Autonomy.strictest().removes_a_stop
    assert Autonomy(False, True, False).removes_a_stop
    assert Autonomy(True, False, False).removes_a_stop
    assert Autonomy(True, True, True).removes_a_stop


def test_the_stops_a_policy_removes_are_named_in_a_fixed_order() -> None:
    assert Policy().removed_stops() == ()
    assert Policy(design_review=False, spec_approval=False).removed_stops() == ("spec", "design")
    assert Policy(proceed_on_deadlock=True).removed_stops() == ("deadlock",)
