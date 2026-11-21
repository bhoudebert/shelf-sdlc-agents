import asyncio
import json
from typing import Any

import pytest

from shelf.adapters.container_runner import service as service_module
from shelf.adapters.container_runner.service import StepService
from shelf.domain.result import Ok
from shelf.domain.stepspec import RunnerRules, StepAsk, container_spec, parse_request
from shelf.domain.stepstream import Exit, Hello, Result, Tool, decode, encode
from shelf.ports.container_engine import EngineError, Finished, Owned
from tests.adapters.container_runner.fakes import FakeEngine

RULES = RunnerRules(image="shelf-step:test")


def ask(**changes: Any) -> StepAsk:
    body: dict[str, Any] = {
        "key": "wf-1/implement/1",
        "repo": "acme/shop",
        "clone": "steps/wf-1/repo",
        "env": {"GH_TOKEN": "t"},
        "input": {"prompt": "go"},
    }
    parsed = parse_request({**body, **changes}, RULES)
    assert isinstance(parsed, Ok), parsed
    return parsed.value


def lines(*events: Any) -> list[bytes]:
    return [(encode(event) + "\n").encode() for event in events]


async def collect(service: StepService, step: StepAsk) -> list[str]:
    return [line async for line in service.follow(service.start(step))]


def kinds(found: list[str]) -> list[str]:
    return [decode(line).__class__.__name__ for line in found]


async def test_a_step_streams_what_the_container_wrote_and_ends_with_the_exit_the_runner_writes() -> None:
    engine = FakeEngine(lines(Hello(), Tool("a", "Bash", "ls"), Result(result="done")))
    found = await collect(StepService(engine, RULES), ask())
    assert kinds(found) == ["Hello", "Tool", "Result", "Exit"]
    assert decode(found[-1]) == Exit(0)
    assert engine.started == ["id-1"]
    assert engine.removed[-1] == "id-1"


async def test_the_container_is_the_one_the_rules_build_and_the_task_is_put_in_a_file() -> None:
    engine = FakeEngine(lines(Hello()))
    step = ask()
    service = StepService(engine, RULES, clock=lambda: 1_000.0)
    await collect(service, step)
    [(spec, name)] = engine.created
    assert spec == container_spec(step, RULES, expires=1_000 + step.limits.seconds + 60)
    assert name.startswith("shelf-step-")
    [(_, directory, filename, data)] = engine.files
    assert (directory, filename, json.loads(data)) == ("/run/shelf", "task.json", {"prompt": "go"})


async def test_asking_again_with_the_same_key_starts_no_second_container() -> None:
    engine = FakeEngine(lines(Hello(), Result(result="x")))
    service = StepService(engine, RULES)
    first = await collect(service, ask())
    second = await collect(service, ask())
    assert first == second
    assert len(engine.created) == 1


async def test_a_line_that_arrives_in_pieces_is_one_line_and_a_last_line_without_a_newline_is_kept() -> None:
    whole = encode(Tool("a", "Bash", "ls"))
    engine = FakeEngine([b'{"e":"hello",', b'"v":1}\n' + whole[:10].encode(), whole[10:].encode()])
    found = await collect(StepService(engine, RULES), ask())
    assert kinds(found) == ["Hello", "Tool", "Exit"]


async def test_a_step_that_runs_out_of_time_is_removed_and_ends_with_a_timeout() -> None:
    engine = FakeEngine(lines(Hello()), hang=True)
    service = StepService(engine, RULES)
    found = await collect(service, ask(limits={"seconds": 1}))
    assert decode(found[-1]) == Exit(-1, "timeout")
    assert engine.killed == ["id-1"]
    assert "id-1" in engine.removed


async def test_stopping_a_step_ends_it_as_killed() -> None:
    engine = FakeEngine(lines(Hello()), hang=True)
    service = StepService(engine, RULES)
    record = service.start(ask())
    await asyncio.sleep(0.05)
    await service.stop(record)
    found = [line async for line in service.follow(record)]
    assert decode(found[-1]) == Exit(0, "killed")


async def test_a_container_the_engine_killed_for_memory_says_so() -> None:
    engine = FakeEngine(lines(Hello()), finished=Finished(137, oom=True))
    found = await collect(StepService(engine, RULES), ask())
    assert decode(found[-1]) == Exit(137, "oom")


async def test_an_engine_failure_ends_the_step_with_a_reason_and_no_detail() -> None:
    found = await collect(StepService(FakeEngine(fail_create=True), RULES), ask())
    assert kinds(found) == ["Exit"]
    assert decode(found[0]) == Exit(-1, "engine")
    assert "500" not in found[0]


async def test_a_step_that_writes_too_much_is_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "MAX_OUTPUT", 50)
    engine = FakeEngine(lines(Hello(), Tool("a", "Bash", "x" * 80), Tool("b", "Bash", "y")), hang=True)
    found = await collect(StepService(engine, RULES), ask())
    assert decode(found[-1]) == Exit(0, "killed")


async def test_a_reader_can_come_back_from_a_cursor_and_gets_a_ping_while_it_waits() -> None:
    engine = FakeEngine(lines(Hello(), Tool("a", "Bash", "ls")), hang=True)
    service = StepService(engine, RULES, ping_every=0.05)
    record = service.start(ask())
    await asyncio.sleep(0.05)
    seen: list[str] = []
    async for line in service.follow(record, 1):
        seen.append(line)
        if len(seen) == 2:
            break
    assert [decode(line).__class__.__name__ for line in seen] == ["Tool", "Ping"]
    assert len(record.lines) == 2
    await service.stop(record)
    await asyncio.sleep(0.05)


async def test_a_finished_step_is_kept_for_a_day_and_then_forgotten() -> None:
    now = [0.0]
    engine = FakeEngine(lines(Hello()))
    service = StepService(engine, RULES, clock=lambda: now[0])
    await collect(service, ask())
    assert service.known("wf-1/implement/1") is not None
    now[0] = 24 * 3600 + 1
    service.start(ask(key="other"))
    assert service.known("wf-1/implement/1") is None


async def test_the_reaper_removes_expired_containers_with_its_label_and_nothing_else() -> None:
    engine = FakeEngine(
        existing=[
            Owned("old", {"shelf.managed": "true", "shelf.expires": "100"}),
            Owned("fresh", {"shelf.managed": "true", "shelf.expires": "9999"}),
            Owned("odd", {"shelf.managed": "true"}),
        ]
    )
    gone = await StepService(engine, RULES, clock=lambda: 500.0).reap()
    assert (gone, engine.removed, engine.killed) == (1, ["old"], ["old"])


async def test_the_reaper_fails_when_the_engine_cannot_be_read() -> None:
    with pytest.raises(EngineError):
        await StepService(FakeEngine(unreadable=True), RULES).reap()
