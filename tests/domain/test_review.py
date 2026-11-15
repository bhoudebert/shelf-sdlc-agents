import pytest

from shelf.domain.pipeline import Phase
from shelf.domain.review import ReviewDepth, review_note


def test_a_quick_review_reports_at_most_three_problems_that_stop_the_work_and_approves_what_can_be_built() -> None:
    note = review_note(ReviewDepth.QUICK, Phase.SPEC_REVIEW)
    assert "at most three" in note
    assert "approve it" in note


def test_a_thorough_review_looks_hard_for_up_to_ten_problems() -> None:
    note = review_note(ReviewDepth.THOROUGH, Phase.DESIGN_REVIEW)
    assert "edge cases, failure modes" in note
    assert "up to ten" in note


def test_the_standard_depth_adds_nothing_to_the_reviewers_own_instructions() -> None:
    assert review_note(ReviewDepth.STANDARD, Phase.SPEC_REVIEW) == ""


@pytest.mark.parametrize("depth", list(ReviewDepth))
@pytest.mark.parametrize("phase", [Phase.CODE_REVIEW, Phase.INTAKE, Phase.DESIGN, Phase.PLAN, Phase.IMPLEMENT])
def test_the_code_review_and_the_producers_are_never_told_a_depth(depth: ReviewDepth, phase: Phase) -> None:
    assert review_note(depth, phase) == ""
