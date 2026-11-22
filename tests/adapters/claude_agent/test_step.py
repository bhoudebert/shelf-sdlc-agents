"""The container side of a step, and that what it writes fills the record as the sandbox path did. No SDK call is made."""

import asyncio
import re
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

from shelf.adapters.claude_agent import step
from shelf.adapters.claude_agent.backend import note_result, usage_of, watch_run
from shelf.adapters.claude_agent.step import events_of, run_step
from shelf.adapters.container_agent.backend import ContainerBackend
from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES
from shelf.domain.stepstream import Event, Exit, encode
from shelf.ports.agents import AgentTask, RunSink
from shelf.ports.step_runner import StepRequest, StepSettings, task_from_input

TOKEN = "ghp_" + "a" * 30


def conversation() -> Sequence[object]:
    return [
        AssistantMessage(
            content=[
                TextBlock("working"),
                ToolUseBlock("t1", "Bash", {"command": f"mvn -q verify {TOKEN}"}),
                ToolUseBlock("t2", "Read", {"file_path": "src/x.py"}),
            ],
            model="m",
        ),
        UserMessage(
            content=[
                ToolResultBlock("t1", [{"type": "text", "text": f"[ERROR] boom {TOKEN}"}], is_error=True),
                ToolResultBlock("t2", "fine", is_error=False),
            ]
        ),
        ResultMessage(
            subtype="success",
            duration_ms=94_000,
            duration_api_ms=80_000,
            is_error=False,
            num_turns=12,
            session_id="s-9",
            stop_reason="end_turn",
            total_cost_usd=0.4213,
            usage={"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 7},
            result="the answer",
            model_usage={"claude-x": {}},  # pyright: ignore[reportArgumentType]
            permission_denials=[{"tool_name": "Bash", "tool_input": {"command": "curl http://evil"}}],
            errors=[f"oops {TOKEN}"],
        ),
    ]


async def replay(items: Sequence[object]) -> AsyncIterator[object]:
    for item in items:
        yield item


def task() -> AgentTask:
    return AgentTask(ROLES[Phase.IMPLEMENT], "system", "prompt", Path("/clone"))


async def lines_of(items: Sequence[object]) -> list[str]:
    written: list[Event] = []
    spec, settings = task_from_input({"role": {"name": "implementer"}, "prompt": "p"}, Path("/work"))
    await run_step(spec, settings, written.append, replay(items))
    return [encode(event) for event in [*written, Exit(0)]]


async def test_the_container_writes_hello_first_and_one_line_per_tool_call_and_the_result() -> None:
    lines = await lines_of(conversation())
    kinds = [line.split('"e":"')[1].split('"')[0] for line in lines]
    assert kinds == ["hello", "tool", "tool", "tool_result", "result", "exit"]


async def test_a_secret_in_a_tool_call_never_leaves_the_container() -> None:
    assert TOKEN not in "".join(await lines_of(conversation()))


async def test_what_the_worker_reads_equals_what_the_sandbox_path_would_have_recorded() -> None:
    sandbox = RunSink()
    pending: dict[str, int] = {}
    for message in conversation():
        watch_run(message, sandbox, pending)
        if isinstance(message, ResultMessage):
            sandbox.usage = usage_of(message)
            sandbox.session_id = message.session_id or ""
            note_result(message, sandbox)

    class Runner:
        async def run(self, request: StepRequest) -> AsyncIterator[str]:
            del request
            for line in await lines_of(conversation()):
                yield line

    container = RunSink()
    await ContainerBackend(Runner()).run(AgentTask(ROLES[Phase.IMPLEMENT], "s", "p", Path("/c"), sink=container))
    for name in ("tools", "usage", "session_id", "denials", "subtype", "stop_reason", "terminal_reason", "errors"):
        assert getattr(container, name) == getattr(sandbox, name), name
    assert container.api_error_status == sandbox.api_error_status


def test_a_message_that_is_none_of_these_writes_nothing() -> None:
    assert events_of(object()) == []
    assert events_of(AssistantMessage(content=[TextBlock("only words")], model="m")) == []


async def test_the_container_turns_the_sdk_sandbox_off_because_it_is_the_boundary() -> None:
    seen: dict[str, object] = {}

    def fake_query(*, prompt: str, options: object) -> AsyncIterator[object]:
        seen["prompt"], seen["options"] = prompt, options
        return replay([])

    original = step.query
    step.query = fake_query  # type: ignore[assignment]
    try:
        spec, settings = task_from_input(
            {"role": {"name": "implementer", "tools": ["Bash"]}, "prompt": "go", "web": True},
            Path("/work"),
        )
        await run_step(spec, StepSettings(web=settings.web), lambda event: None)
    finally:
        step.query = original
    options = seen["options"]
    assert seen["prompt"] == "go"
    assert options.sandbox["enabled"] is False  # type: ignore[attr-defined]
    assert "WebFetch" in options.allowed_tools  # type: ignore[attr-defined]


async def test_a_step_whose_agent_dies_says_what_kind_of_error_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    async def broken(**_: object) -> AsyncIterator[object]:
        message = f"the CLI failed with {TOKEN}"
        raise RuntimeError(message)
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(step, "query", broken)
    task_file = tmp_path / "task.json"
    task_file.write_text('{"role": {"name": "implementer"}, "prompt": "go"}', encoding="utf-8")
    code = await asyncio.to_thread(step.main, [str(task_file)])
    seen = capsys.readouterr()
    assert code == 1
    assert '"e":"hello"' in seen.out
    assert "RuntimeError" in seen.err
    assert TOKEN not in seen.out + seen.err


def _write_task(tmp_path: Path) -> Path:
    import json  # noqa: PLC0415

    task = tmp_path / "task.json"
    task.write_text(json.dumps({"prompt": "go", "role": {"name": "implementer", "tools": []}}))
    return task


def _lines(capsys: pytest.CaptureFixture[str]) -> list[Event]:
    from shelf.domain.stepstream import decode  # noqa: PLC0415

    return [decode(line) for line in capsys.readouterr().out.splitlines()]


def test_a_step_whose_model_host_does_not_resolve_says_so_at_once_and_never_starts_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import socket  # noqa: PLC0415

    from shelf.domain.stepstream import Hello, Result  # noqa: PLC0415

    for name in ("HTTPS_PROXY", "ALL_PROXY", "https_proxy", "all_proxy", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    started: list[str] = []

    def no_such_host(host: str, *_args: object, **_kwargs: object) -> list[object]:
        raise socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")

    async def fake_run_step(*_args: object, **_kwargs: object) -> None:
        started.append("the agent")

    monkeypatch.setattr(socket, "getaddrinfo", no_such_host)
    monkeypatch.setattr(step, "run_step", fake_run_step)

    assert step.main([str(_write_task(tmp_path))]) == 0

    events = _lines(capsys)
    assert isinstance(events[0], Hello)
    result = next(e for e in events if isinstance(e, Result))
    assert result.is_error
    assert re.search(r"api\.anthropic\.com", result.result)
    assert "SHELF_STEP_DNS" in result.result
    assert started == []


def test_the_host_that_is_checked_is_the_one_of_the_base_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import socket  # noqa: PLC0415

    from shelf.domain.stepstream import Result  # noqa: PLC0415

    for name in ("HTTPS_PROXY", "ALL_PROXY", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://gateway.internal:8080/v1")
    asked: list[str] = []

    def no_such_host(host: str, *_args: object, **_kwargs: object) -> list[object]:
        asked.append(host)
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", no_such_host)

    step.main([str(_write_task(tmp_path))])

    assert asked == ["gateway.internal"]
    assert any(isinstance(e, Result) and "gateway.internal" in e.result for e in _lines(capsys))


def test_a_step_behind_a_proxy_does_not_look_the_name_up_and_starts_the_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket  # noqa: PLC0415

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    started: list[str] = []

    def never(*_args: object, **_kwargs: object) -> list[object]:
        message = "the proxy resolves, not the step"
        raise AssertionError(message)

    async def fake_run_step(*_args: object, **_kwargs: object) -> None:
        started.append("the agent")

    monkeypatch.setattr(socket, "getaddrinfo", never)
    monkeypatch.setattr(step, "run_step", fake_run_step)

    assert step.main([str(_write_task(tmp_path))]) == 0
    assert started == ["the agent"]


def test_a_step_whose_model_host_resolves_starts_the_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import socket  # noqa: PLC0415

    for name in ("HTTPS_PROXY", "ALL_PROXY", "https_proxy", "all_proxy", "ANTHROPIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    started: list[str] = []

    async def fake_run_step(*_args: object, **_kwargs: object) -> None:
        started.append("the agent")

    def resolves(*_args: object, **_kwargs: object) -> list[object]:
        return [("ok",)]

    monkeypatch.setattr(socket, "getaddrinfo", resolves)
    monkeypatch.setattr(step, "run_step", fake_run_step)

    assert step.main([str(_write_task(tmp_path))]) == 0
    assert started == ["the agent"]


def test_the_agents_step_gives_its_commands_the_one_jdk_the_worker_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json  # noqa: PLC0415
    import os  # noqa: PLC0415

    home = tmp_path / "home"
    (home / ".local/share/mise/installs/java/temurin-27.0.1+0/bin").mkdir(parents=True)
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")
    seen: dict[str, str] = {}

    async def fake_run_step(*_args: object, **_kwargs: object) -> None:
        seen.update({"JAVA_HOME": os.environ.get("JAVA_HOME", ""), "PATH": os.environ["PATH"]})

    monkeypatch.setattr(step, "run_step", fake_run_step)
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"prompt": "go", "role": {"name": "implementer", "tools": []}}))

    assert step.main([str(task)], home=home) == 0

    java_home = f"{home}/.local/share/mise/installs/java/temurin-27.0.1+0"
    assert seen == {"JAVA_HOME": java_home, "PATH": f"{java_home}/bin:/usr/bin"}


def test_the_jdks_of_a_home_are_its_folders_and_never_a_link_or_a_file(tmp_path: Path) -> None:
    root = tmp_path / ".local/share/mise/installs/java"
    (root / "temurin-27.0.1+0").mkdir(parents=True)
    (root / "latest").symlink_to("temurin-27.0.1+0")
    (root / "notes.txt").write_text("x")

    assert step.installed_jdks(tmp_path) == ["temurin-27.0.1+0"]
    assert step.installed_jdks(tmp_path / "nowhere") == []
