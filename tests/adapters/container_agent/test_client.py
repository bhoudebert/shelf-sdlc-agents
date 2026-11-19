import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from shelf.adapters.container_agent.backend import ContainerBackend
from shelf.adapters.container_agent.client import HttpStepRunner, RunnerError, body_of
from shelf.adapters.container_runner.app import create_app
from shelf.adapters.container_runner.service import StepService
from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES
from shelf.domain.stepspec import RunnerRules
from shelf.domain.stepstream import Hello, Result, Tool, encode
from shelf.ports.agents import AgentTask, RunSink
from shelf.ports.step_runner import StepRequest
from tests.adapters.container_runner.fakes import FakeEngine


def request(**changes: object) -> StepRequest:
    fields: dict[str, object] = {
        "key": "k-1",
        "repo": "acme/shop",
        "clone": "steps/wf-1",
        "session": "work/wf-1",
        "env": {"GH_TOKEN": "t"},
        "input": {"prompt": "go"},
    }
    return StepRequest(**{**fields, **changes})  # pyright: ignore[reportArgumentType]


def test_the_body_holds_the_fixed_fields_and_a_reviewer_reads_the_tools() -> None:
    assert body_of(request()) == {
        "key": "k-1",
        "kind": "agent",
        "repo": "acme/shop",
        "clone": "steps/wf-1",
        "session": "work/wf-1",
        "mode": {"tools": "rw"},
        "env": {"GH_TOKEN": "t"},
        "input": {"prompt": "go"},
    }
    body = body_of(request(tools_readonly=True, limits={"seconds": 60}))
    assert body["mode"] == {"tools": "ro"}
    assert body["limits"] == {"seconds": 60}


async def lines_of(runner: HttpStepRunner) -> list[str]:
    return [line async for line in runner.run(request())]


async def test_the_lines_come_back_without_blank_ones_and_the_token_goes_in_the_header() -> None:
    seen: list[httpx.Request] = []

    def handle(call: httpx.Request) -> httpx.Response:
        seen.append(call)
        return httpx.Response(200, text='{"e":"hello","v":1}\n\n{"e":"exit","code":0}\n')

    runner = HttpStepRunner(token="secret", transport=httpx.MockTransport(handle))
    assert await lines_of(runner) == ['{"e":"hello","v":1}', '{"e":"exit","code":0}']
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert json.loads(seen[0].content)["key"] == "k-1"


async def test_a_refusal_is_an_error_that_says_why() -> None:
    def handle(call: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "the field repo is missing"})

    with pytest.raises(RunnerError, match=r"422.*the field repo"):
        await lines_of(HttpStepRunner(transport=httpx.MockTransport(handle)))


async def test_a_runner_that_cannot_be_reached_is_an_error_without_the_path() -> None:
    def handle(call: httpx.Request) -> httpx.Response:
        message = "no socket at /run/secret/path"
        raise httpx.ConnectError(message)

    with pytest.raises(RunnerError, match="could not be reached: ConnectError") as caught:
        await lines_of(HttpStepRunner(transport=httpx.MockTransport(handle)))
    assert "/run/secret/path" not in str(caught.value)


class WithClone:
    """The volumes arrive in stage 3: until then a test names the repository and the clone itself."""

    def __init__(self, runner: HttpStepRunner) -> None:
        self.runner = runner

    def run(self, request: StepRequest) -> AsyncIterator[str]:
        return self.runner.run(replace(request, repo="acme/shop", clone="steps/wf-1"))


async def test_the_backend_reads_a_whole_step_from_the_runner_service_with_a_fake_engine() -> None:
    rules = RunnerRules(image="shelf-step:test")
    output = [Hello(), Tool("a", "Bash", "mvn verify"), Result(result="the answer", session="s-1")]
    engine = FakeEngine([("\n".join(encode(event) for event in output) + "\n").encode()])
    app = create_app(StepService(engine, rules), rules, "secret")
    http = HttpStepRunner(token="secret", transport=httpx.ASGITransport(app=app))
    sink = RunSink()
    task = AgentTask(ROLES[Phase.IMPLEMENT], "system", "prompt", Path("/clone"), sink=sink)
    answer = await ContainerBackend(WithClone(http), new_key=lambda: "k-9").run(task)
    assert (answer, sink.session_id) == ("the answer", "s-1")
    assert [tool.name for tool in sink.tools] == ["Bash"]
    [(spec, _)] = engine.created
    assert spec["HostConfig"]["ReadonlyRootfs"] is True
