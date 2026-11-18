from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shelf.adapters.container_agent.backend import ContainerBackend, StepFailedError
from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES
from shelf.domain.runlog import ToolEvent
from shelf.domain.stepstream import Audit, Event, Exit, Hello, Ping, Result, Tool, ToolResult, encode
from shelf.domain.usage import Usage
from shelf.ports.agents import AgentTask, RunSink
from shelf.ports.step_runner import StepRequest, task_from_input


class FakeRunner:
    """Stands in for the runner service: plays a script of lines per call and remembers what it was asked."""

    def __init__(self, *scripts: list[str]) -> None:
        self.scripts = list(scripts)
        self.requests: list[StepRequest] = []

    async def run(self, request: StepRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        for line in self.scripts.pop(0):
            yield line


def good(answer: str = "the answer", session: str = "s-1") -> list[str]:
    usage = Usage(1, 2, 3, 4, 0.25, 5, 6.0, ("m",))
    events: list[Event] = [
        Hello(),
        Tool("a", "Bash", "mvn verify"),
        ToolResult("a", True, "[ERROR] boom"),
        Audit(2),
        Ping(),
        Result(
            result=answer,
            session=session,
            usage=usage,
            subtype="success",
            stop_reason="end_turn",
            denials=("Bash: curl http://x",),
        ),
        Exit(0),
    ]
    return [encode(event) for event in events]


def task(sink: RunSink | None = None, **changes: object) -> AgentTask:
    fields: dict[str, object] = {
        "role": ROLES[Phase.IMPLEMENT],
        "system_prompt": "system",
        "prompt": "prompt",
        "workdir": Path("/clone"),
        "env": {"GH_TOKEN": "t"},
        "max_turns": 7,
        "max_budget_usd": 1.5,
        "model": "m",
        "sink": sink,
    }
    return AgentTask(**{**fields, **changes})  # pyright: ignore[reportArgumentType]


async def test_a_step_returns_the_answer_and_fills_the_record_like_the_sandbox_path() -> None:
    sink = RunSink()
    answer = await ContainerBackend(FakeRunner(good())).run(task(sink))
    assert answer == "the answer"
    assert sink.tools == [ToolEvent("Bash", "mvn verify", ok=False, note="[ERROR] boom")]
    assert sink.usage == Usage(1, 2, 3, 4, 0.25, 5, 6.0, ("m",))
    assert (sink.session_id, sink.subtype, sink.stop_reason) == ("s-1", "success", "end_turn")
    assert sink.denials == ["Bash: curl http://x"]
    assert (sink.error, sink.fell_back) == ("", False)


async def test_the_request_carries_the_task_and_the_environment_apart() -> None:
    runner = FakeRunner(good())
    backend = ContainerBackend(
        runner,
        web=True,
        allowed_domains=("a.org",),
        bindings=lambda role: ("superpowers",) if role == "implementer" else (),
        extra_domains=lambda: ("b.org", "a.org"),
        new_key=lambda: "k-1",
    )
    await backend.run(task())
    [request] = runner.requests
    assert (request.key, request.kind, dict(request.env)) == ("k-1", "agent", {"GH_TOKEN": "t"})
    assert "GH_TOKEN" not in repr(request.input)
    rebuilt, settings = task_from_input(request.input, Path("/work"))
    assert (rebuilt.role, rebuilt.prompt, rebuilt.max_turns, rebuilt.max_budget_usd, rebuilt.model) == (
        ROLES[Phase.IMPLEMENT],
        "prompt",
        7,
        1.5,
        "m",
    )
    assert (settings.web, settings.allowed_domains, settings.bundles) == (True, ("a.org", "b.org"), ("superpowers",))


async def test_an_error_the_agent_reports_fails_the_step_with_its_own_words() -> None:
    sink = RunSink()
    script = [encode(e) for e in (Hello(), Result(is_error=True, result="max turns reached"), Exit(0))]
    with pytest.raises(StepFailedError, match="implementer failed: max turns reached"):
        await ContainerBackend(FakeRunner(script)).run(task(sink))
    assert sink.error == "max turns reached"


async def test_a_stream_that_stops_fails_the_step_and_keeps_what_it_saw() -> None:
    sink = RunSink()
    script = good()[:-1]
    with pytest.raises(StepFailedError, match="without an exit"):
        await ContainerBackend(FakeRunner(script)).run(task(sink))
    assert sink.tools
    assert "without an exit" in sink.error


async def test_a_timeout_names_the_time_limit() -> None:
    script = [encode(e) for e in (Hello(), Tool("a", "Bash", "sleep"), Exit(-1, "timeout"))]
    with pytest.raises(StepFailedError, match="out of time"):
        await ContainerBackend(FakeRunner(script)).run(task())


async def test_a_line_that_breaks_the_protocol_fails_the_step_without_repeating_it() -> None:
    sink = RunSink()
    with pytest.raises(StepFailedError) as caught:
        await ContainerBackend(FakeRunner([encode(Hello()), "ghp_" + "a" * 30])).run(task(sink))
    assert "ghp_" not in str(caught.value) + sink.error


async def test_a_session_that_cannot_be_continued_starts_again_from_the_whole_task() -> None:
    sink = RunSink()
    failed = [encode(e) for e in (Hello(), Result(is_error=True, result="no such session"), Exit(0))]
    runner = FakeRunner(failed, good("fresh", "s-2"))
    answer = await ContainerBackend(runner).run(task(sink, resume="s-1", fallback_prompt="the whole task"))
    assert (answer, sink.fell_back, sink.session_id) == ("fresh", True, "s-2")
    assert [(r.input["resume"], r.input["prompt"]) for r in runner.requests] == [
        ("s-1", "prompt"),
        ("", "the whole task"),
    ]


async def test_a_step_that_never_continued_a_session_does_not_run_twice() -> None:
    failed = [encode(e) for e in (Hello(), Result(is_error=True, result="boom"), Exit(0))]
    runner = FakeRunner(failed, good())
    with pytest.raises(StepFailedError):
        await ContainerBackend(runner).run(task())
    assert len(runner.requests) == 1


async def test_every_step_gets_a_key_of_its_own_when_none_is_given() -> None:
    runner = FakeRunner(good(), good())
    backend = ContainerBackend(runner)
    await backend.run(task())
    await backend.run(task())
    assert runner.requests[0].key != runner.requests[1].key
