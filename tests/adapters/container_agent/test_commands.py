from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shelf.adapters.container_agent.backend import Volumes
from shelf.adapters.container_agent.client import RunnerError
from shelf.adapters.container_agent.commands import ContainerCommands
from shelf.domain.stepstream import Check, Event, Exit, Hello, Ping, encode
from shelf.ports.step_runner import StepRequest
from shelf.ports.workspace import CheckResult


class FakeRunner:
    """Stands in for the runner service: plays one script of lines per call and remembers what it was asked."""

    def __init__(self, *scripts: list[str] | Exception) -> None:
        self.scripts = list(scripts)
        self.requests: list[StepRequest] = []

    async def run(self, request: StepRequest) -> AsyncIterator[str]:
        self.requests.append(request)
        script = self.scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        for line in script:
            yield line


def lines(*events: Event) -> list[str]:
    return [encode(event) for event in events]


def volumes(tmp_path: Path) -> Volumes:
    return Volumes(tmp_path / "steps", tmp_path / "tools", tmp_path / "sessions")


def clone(where: Volumes) -> Path:
    return where.steps / "steps" / "shelf-a1" / "repo"


async def run(
    runner: FakeRunner, tmp_path: Path, *, command: str = "./mvnw -B verify", docker: bool = False
) -> CheckResult:
    where = volumes(tmp_path)
    commands = ContainerCommands(runner, where, docker=docker)
    return await commands.run("acme/shop", clone(where), command)


async def test_a_command_that_passes_is_a_result_with_exit_zero_and_its_output(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, "BUILD SUCCESS\n"), Exit(0)))

    assert await run(runner, tmp_path) == CheckResult("./mvnw -B verify", 0, "BUILD SUCCESS\n")


async def test_a_command_that_fails_keeps_its_exit_code_and_what_it_said(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(1, "[ERROR] Tests run: 3, Failures: 1"), Exit(0)))

    assert await run(runner, tmp_path) == CheckResult("./mvnw -B verify", 1, "[ERROR] Tests run: 3, Failures: 1")


async def test_the_request_is_a_check_with_the_clone_the_repository_the_command_and_no_credential(
    tmp_path: Path,
) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, ""), Exit(0)))

    await run(runner, tmp_path, command="make test")

    [request] = runner.requests
    assert request.kind == "check"
    assert (request.repo, request.clone, request.session) == ("acme/shop", "steps/shelf-a1/repo", "")
    assert dict(request.input) == {"command": "make test"}
    assert dict(request.env) == {}
    assert request.tools_readonly is False
    assert request.docker is False
    assert str(tmp_path) not in str(request)


async def test_the_folders_the_runner_mounts_are_made_first(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, ""), Exit(0)))

    await run(runner, tmp_path)

    home = tmp_path / "tools" / "home" / "acme__shop"
    assert (home / ".m2").is_dir()
    assert (home / ".local" / "share" / "mise").is_dir()


async def test_a_check_asks_for_docker_when_the_operator_turned_it_on(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, ""), Exit(0)))

    await run(runner, tmp_path, docker=True)

    assert runner.requests[0].docker is True


async def test_each_check_is_a_step_of_its_own_with_its_own_key(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, ""), Exit(0)), lines(Hello(), Check(0, ""), Exit(0)))
    where = volumes(tmp_path)
    commands = ContainerCommands(runner, where)

    await commands.run("acme/shop", clone(where), "a")
    await commands.run("acme/shop", clone(where), "b")

    assert runner.requests[0].key != runner.requests[1].key


async def test_a_check_that_ran_out_of_time_fails_and_says_so(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Ping(), Exit(-1, "timeout")))

    result = await run(runner, tmp_path)

    assert result.exit_code != 0
    assert "ran out of time" in result.output


async def test_a_stream_that_breaks_fails_the_check_and_says_why(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello()))  # no exit line

    result = await run(runner, tmp_path)

    assert result.exit_code != 0
    assert "without an exit" in result.output


async def test_a_line_that_is_not_json_fails_the_check_without_repeating_the_line(tmp_path: Path) -> None:
    runner = FakeRunner(["not json with a secret ghp_" + "a" * 30])

    result = await run(runner, tmp_path)

    assert result.exit_code != 0
    assert "ghp_" not in result.output


async def test_a_runner_that_cannot_be_reached_fails_the_check_and_says_why(tmp_path: Path) -> None:
    runner = FakeRunner(RunnerError("the runner refused the request: the field docker is refused"))

    result = await run(runner, tmp_path)

    assert result.exit_code != 0
    assert "the field docker is refused" in result.output


async def test_a_check_that_could_not_run_is_never_a_pass(tmp_path: Path) -> None:
    for script in (lines(Hello()), lines(Hello(), Exit(0)), lines(Hello(), Exit(3))):
        result = await run(FakeRunner(script), tmp_path)
        assert result.exit_code != 0, script


async def test_a_clone_outside_the_shared_volume_fails_the_check_and_says_why(tmp_path: Path) -> None:
    runner = FakeRunner(lines(Hello(), Check(0, ""), Exit(0)))
    commands = ContainerCommands(runner, volumes(tmp_path))

    result = await commands.run("acme/shop", Path("/elsewhere/repo"), "make test")

    assert result.exit_code != 0
    assert "SHELF_STEPS_DIR" in result.output
    assert runner.requests == []


@pytest.mark.parametrize("output", ["a" * 50_000])
async def test_the_output_is_passed_on_as_the_step_wrote_it(tmp_path: Path, output: str) -> None:
    runner = FakeRunner(lines(Hello(), Check(2, output), Exit(0)))

    assert (await run(runner, tmp_path)).output == output
