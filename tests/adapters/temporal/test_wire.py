from shelf.adapters.temporal.wire import StepOutput, output_of, result_of
from shelf.domain.work import Verified


def test_a_result_recorded_without_the_waiting_field_is_not_waiting() -> None:
    assert result_of(StepOutput("verified", passed=True)) == Verified(passed=True)


def test_a_waiting_result_survives_the_trip_through_the_history() -> None:
    waiting = Verified(passed=False, report="still running", waiting=True)
    assert result_of(output_of(waiting)) == waiting
