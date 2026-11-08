from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.polling import next_interval


def test_the_interval_doubles_until_the_ceiling() -> None:
    ceiling = timedelta(minutes=15)
    assert next_interval(timedelta(seconds=30), ceiling) == timedelta(minutes=1)
    assert next_interval(timedelta(minutes=10), ceiling) == ceiling


@given(st.integers(1, 3600), st.integers(1, 3600))
def test_the_interval_never_shrinks_below_the_ceiling_nor_passes_it(seconds: int, ceiling_seconds: int) -> None:
    current, ceiling = timedelta(seconds=seconds), timedelta(seconds=ceiling_seconds)
    following = next_interval(current, ceiling)
    assert following <= ceiling
    assert following >= min(current, ceiling)
