from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.polling import Mode, next_interval, poll_bounds


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


def test_a_local_instance_looks_often_and_a_server_instance_leaves_it_to_webhooks() -> None:
    local_base, local_ceiling = poll_bounds(Mode.LOCAL)
    server_base, server_ceiling = poll_bounds(Mode.SERVER)
    assert local_base < server_base
    assert local_ceiling < server_ceiling
