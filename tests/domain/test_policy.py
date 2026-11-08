import pytest

from shelf.domain.pipeline import PIPELINE, EntryPoint, Phase
from shelf.domain.policy import Policy, course_for


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
