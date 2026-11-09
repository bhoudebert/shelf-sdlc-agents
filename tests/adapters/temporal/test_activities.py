import asyncio

from shelf.adapters.temporal.activities import keep_alive


async def test_a_busy_step_is_kept_alive_until_it_ends() -> None:
    beats: list[int] = []
    beating = asyncio.create_task(keep_alive(lambda: beats.append(1), 0.01))
    await asyncio.sleep(0.1)
    beating.cancel()
    await asyncio.gather(beating, return_exceptions=True)
    assert len(beats) >= 3
    seen = len(beats)
    await asyncio.sleep(0.05)
    assert len(beats) == seen  # silent once cancelled
