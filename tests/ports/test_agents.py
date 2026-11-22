from pathlib import Path

import pytest

from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES
from shelf.domain.usage import Usage
from shelf.ports.agents import GO_ON, OUT_OF_TURNS, AgentTask, RunSink, go_on_after_turns


def task(sink: RunSink) -> AgentTask:
    return AgentTask(ROLES[Phase.IMPLEMENT], "system", "do it", Path("/work"), sink=sink)


class Runs:
    """Plays one outcome per run: an answer, or the way a run ends badly (subtype, session)."""

    def __init__(self, *outcomes: str | tuple[str, str]) -> None:
        self.outcomes = list(outcomes)
        self.tasks: list[AgentTask] = []

    async def __call__(self, asked: AgentTask) -> str:
        self.tasks.append(asked)
        outcome = self.outcomes.pop(0)
        assert asked.sink is not None
        asked.sink.usage = Usage(turns=40, cost_usd=1.0)
        if isinstance(outcome, str):
            return outcome
        asked.sink.subtype, asked.sink.session_id = outcome
        asked.sink.error = "Reached maximum number of turns"
        raise RuntimeError(asked.sink.error)


async def test_a_run_out_of_turns_goes_on_in_its_own_session_and_the_use_is_added() -> None:
    sink = RunSink()
    runs = Runs((OUT_OF_TURNS, "s-1"), "done")
    assert await go_on_after_turns(runs, task(sink)) == "done"
    assert (runs.tasks[1].resume, runs.tasks[1].prompt) == ("s-1", GO_ON)
    assert sink.usage == Usage(turns=80, cost_usd=2.0)
    assert sink.error == ""


async def test_a_second_run_out_of_turns_fails_the_step_with_the_use_of_both() -> None:
    sink = RunSink()
    with pytest.raises(RuntimeError):
        await go_on_after_turns(Runs((OUT_OF_TURNS, "s-1"), (OUT_OF_TURNS, "s-1")), task(sink))
    assert sink.usage == Usage(turns=80, cost_usd=2.0)


@pytest.mark.parametrize("ending", [("error_during_execution", "s-1"), (OUT_OF_TURNS, "")])
async def test_any_other_failure_is_not_continued(ending: tuple[str, str]) -> None:
    runs = Runs(ending)
    with pytest.raises(RuntimeError):
        await go_on_after_turns(runs, task(RunSink()))
    assert len(runs.tasks) == 1
