import pytest

from shelf.domain.ci import Ci, CiRun, CiState, judge


def done(conclusion: str, name: str = "build") -> CiRun:
    return CiRun(name, "completed", conclusion)


def running(name: str = "slow") -> CiRun:
    return CiRun(name, "in_progress")


def test_no_run_at_all_is_no_ci() -> None:
    assert judge([]) == Ci(CiState.NONE)


@pytest.mark.parametrize("conclusion", ["success", "neutral", "skipped"])
def test_finished_runs_that_passed_are_green(conclusion: str) -> None:
    assert judge([done("success", "a"), done(conclusion, "b")]).state is CiState.GREEN


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "startup_failure", "stale", "something_new"])
def test_a_run_that_did_not_pass_is_red_even_when_it_only_timed_out_or_never_started(conclusion: str) -> None:
    ci = judge([done("success", "a"), done(conclusion, "b")])
    assert ci.state is CiState.RED
    assert [run.name for run in ci.failing] == ["b"]


def test_a_run_still_going_is_pending() -> None:
    assert judge([done("success"), running()]).state is CiState.PENDING


def test_red_wins_over_pending_because_waiting_for_a_failed_commit_is_pointless() -> None:
    assert judge([done("failure"), running()]).state is CiState.RED


def test_a_run_that_waits_for_approval_blocks_without_being_red() -> None:
    ci = judge([done("success", "a"), done("action_required", "b")])
    assert ci.state is CiState.BLOCKED
    assert ci.failing == ()
    assert "approve" in ci.report()


def test_the_report_names_each_red_run_with_what_it_says_and_what_still_runs() -> None:
    red = CiRun("test", "completed", "failure", "https://ci/1", "tests/a.py:3 boom")
    report = judge([red, running("lint")]).report()
    assert "test: failure (https://ci/1)" in report
    assert "tests/a.py:3 boom" in report
    assert "Still running: lint" in report


def run(name: str, status: str, conclusion: str = "") -> CiRun:
    return CiRun(name, status, conclusion)


def test_a_cancelled_run_is_not_a_failure_the_ci_is_unfinished_and_says_what_it_waits_for() -> None:
    ci = judge([run("lint", "completed", "success"), run("Specs validate", "completed", "cancelled")])
    assert ci.state is CiState.PENDING
    assert not ci.settled
    assert ci.only_cancelled
    assert "Cancelled, waiting for a newer run to replace them: Specs validate" in ci.report()
    assert ci.failing == ()


def test_a_run_that_failed_makes_the_ci_red_whatever_else_was_cancelled() -> None:
    ci = judge([run("test", "completed", "failure"), run("Specs validate", "completed", "cancelled")])
    assert ci.state is CiState.RED
    assert [r.name for r in ci.failing] == ["test"]
    assert not ci.only_cancelled


def test_a_cancelled_run_beside_one_that_is_running_is_simply_unfinished() -> None:
    ci = judge([run("Specs validate", "completed", "cancelled"), run("test", "in_progress")])
    assert ci.state is CiState.PENDING
    assert not ci.only_cancelled


def test_when_nothing_replaced_the_cancelled_runs_the_ci_is_given_up_as_red_and_names_them() -> None:
    ci = judge([run("Specs validate", "completed", "cancelled")]).given_up()
    assert ci.state is CiState.RED
    assert [r.name for r in ci.failing] == ["Specs validate"]
    assert "Specs validate: cancelled" in ci.report()
