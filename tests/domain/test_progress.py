from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Policy, course_for
from shelf.domain.progress import Entry, Position, describe, marker, render_progress
from shelf.domain.work import Outcome, Produced, Reason, Reviewed, Verdict, Verified


def test_each_kind_of_result_is_described_in_a_few_words() -> None:
    assert describe(Produced(), 0) == "written"
    assert describe(Produced(), 2) == "written (round 2)"
    assert describe(Reviewed(Verdict.APPROVE), 0) == "approved"
    assert describe(Reviewed(Verdict.CHANGES), 1) == "asked for changes (round 1)"
    assert describe(Reviewed(Verdict.ESCALATE), 0).startswith("could not decide")
    assert describe(Verified(passed=True), 0) == "passed"
    assert describe(Verified(passed=False), 1) == "failed (round 1)"


def render(log: list[Entry], phase: Phase, waiting: Reason | None = None, outcome: Outcome | None = None) -> str:
    phases = course_for(EntryPoint.NEED, Policy()).phases
    return render_progress("work-1", phases, log, Position(phase, waiting, outcome))


def test_the_comment_carries_the_marker_the_system_finds_it_by() -> None:
    assert render([], Phase.INTAKE).startswith(marker("work-1"))


def test_every_step_of_the_course_has_a_row_and_steps_not_reached_are_blank() -> None:
    text = render([Entry(Phase.INTAKE, "written")], Phase.SPEC_REVIEW)
    assert "| Writing the spec | ✅ written |" in text
    assert "| Reviewing the spec | ⏳ reviewing the spec |" in text
    assert "| Designing | · |" in text


def test_a_loop_shows_as_a_path_through_its_rounds() -> None:
    log = [
        Entry(Phase.SPEC_REVIEW, "asked for changes"),
        Entry(Phase.SPEC_REVIEW, "approved (round 1)"),
    ]
    assert "| Reviewing the spec | 🔁 asked for changes → ✅ approved (round 1) |" in render(log, Phase.DESIGN)


def test_waiting_for_a_person_and_the_merge_are_said_plainly() -> None:
    assert "**Now:** ⏸ waiting for you: spec approval" in render([], Phase.SPEC_APPROVAL, Reason.GATE)
    assert "**Now:** ✅ ready to review and merge" in render([], Phase.PULL_REQUEST, Reason.MERGE)


def test_a_finished_work_says_how_it_ended_and_shows_no_current_step() -> None:
    text = render([Entry(Phase.INTAKE, "written")], Phase.PULL_REQUEST, outcome=Outcome.MERGED)
    assert "**Now:** ✅ merged" in text
    assert "⏳" not in text
    assert "**Now:** aborted" in render([], Phase.PLAN, outcome=Outcome.ABORTED)
