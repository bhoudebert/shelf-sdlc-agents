from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.pipeline import FIRST_PHASE, PIPELINE, EntryPoint, Phase, phases_from


def test_every_entry_point_has_a_first_phase() -> None:
    assert set(FIRST_PHASE) == set(EntryPoint)


def test_starting_at_a_need_runs_the_whole_pipeline() -> None:
    assert phases_from(EntryPoint.NEED) == PIPELINE


def test_reviewing_a_pull_request_skips_everything_before_code_review() -> None:
    assert phases_from(EntryPoint.PULL_REQUEST_REVIEW)[0] is Phase.CODE_REVIEW


@given(st.sampled_from(EntryPoint))
def test_the_phases_from_an_entry_point_are_a_suffix_of_the_pipeline(entry: EntryPoint) -> None:
    phases = phases_from(entry)
    assert phases == PIPELINE[len(PIPELINE) - len(phases) :]
    assert phases[0] is FIRST_PHASE[entry]
    assert phases[-1] is Phase.PULL_REQUEST
