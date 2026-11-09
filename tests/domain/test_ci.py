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


@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "timed_out", "startup_failure", "stale", "something_new"]
)
def test_a_run_that_did_not_pass_is_red_even_when_it_was_only_cancelled_or_timed_out(conclusion: str) -> None:
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
