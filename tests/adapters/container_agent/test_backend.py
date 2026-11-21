from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from shelf.adapters.container_agent.backend import ContainerBackend, StepFailedError, Volumes
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


def volumes(tmp_path: Path) -> Volumes:
    return Volumes(tmp_path / "steps", tmp_path / "tools", tmp_path / "sessions")


async def test_the_request_names_the_clone_the_repository_and_the_works_session(tmp_path: Path) -> None:
    runner = FakeRunner(good())
    where = volumes(tmp_path)
    backend = ContainerBackend(runner, volumes=where)
    clone = where.steps / "steps" / "shelf-ab_1" / "repo"
    await backend.run(task(workdir=clone, repo="acme/shop", work="work-1", read_only_tools=False))
    request = runner.requests[0]
    assert (request.repo, request.clone, request.session) == ("acme/shop", "steps/shelf-ab_1/repo", "work/work-1")
    assert request.tools_readonly is False
    assert str(tmp_path) not in str(request)


async def test_a_reviewer_asks_for_the_tools_read_only(tmp_path: Path) -> None:
    runner = FakeRunner(good())
    where = volumes(tmp_path)
    await ContainerBackend(runner, volumes=where).run(
        task(workdir=where.steps / "steps" / "a" / "repo", repo="acme/shop", work="w", read_only_tools=True)
    )
    assert runner.requests[0].tools_readonly is True


async def test_the_folders_the_runner_mounts_are_made_before_it_is_asked(tmp_path: Path) -> None:
    where = volumes(tmp_path)
    await ContainerBackend(FakeRunner(good()), volumes=where).run(
        task(workdir=where.steps / "steps" / "a" / "repo", repo="acme/shop", work="work-1")
    )
    home = where.tools / "home" / "acme__shop"
    assert all((home / folder).is_dir() for folder in (".local/share/mise", ".m2", ".npm", ".cache"))
    assert (where.sessions / "work" / "work-1").is_dir()


async def test_a_clone_outside_the_shared_volume_stops_the_step_without_asking_the_runner(tmp_path: Path) -> None:
    runner = FakeRunner()
    with pytest.raises(StepFailedError, match="shared clones volume"):
        await ContainerBackend(runner, volumes=volumes(tmp_path)).run(
            task(workdir=Path("/tmp/elsewhere/repo"), repo="acme/shop", work="w")  # noqa: S108
        )
    assert runner.requests == []


async def test_the_workers_own_variables_are_not_sent(tmp_path: Path) -> None:
    runner = FakeRunner(good())
    env = {"GH_TOKEN": "t", "HOME": "/cache/home/x", "PATH": "/x", "MISE_YES": "1", "CLAUDE_CODE_OAUTH_TOKEN": "o"}
    await ContainerBackend(runner).run(task(env=env))
    assert dict(runner.requests[0].env) == {"GH_TOKEN": "t", "CLAUDE_CODE_OAUTH_TOKEN": "o"}


async def test_the_step_gets_the_model_credential_the_worker_was_given() -> None:
    runner = FakeRunner(good())
    await ContainerBackend(runner, model_env={"CLAUDE_CODE_OAUTH_TOKEN": "tok", "HOME": "/root"}).run(
        task(env={"GH_TOKEN": "gh"})
    )
    assert runner.requests[0].env == {"CLAUDE_CODE_OAUTH_TOKEN": "tok", "GH_TOKEN": "gh"}


async def test_without_a_credential_the_request_holds_none_and_the_credential_never_shows_in_a_repr() -> None:
    runner = FakeRunner(good())
    await ContainerBackend(runner).run(task(env={}))
    assert runner.requests[0].env == {}
    assert "tok-secret" not in repr(ContainerBackend(runner, model_env={"ANTHROPIC_API_KEY": "tok-secret"}))


@pytest.mark.parametrize(
    ("phase", "has_docker"),
    [
        (Phase.IMPLEMENT, True),
        (Phase.CODE_REVIEW, True),
        (Phase.DESIGN, False),
        (Phase.INTAKE, False),
        (Phase.PLAN, False),
    ],
)
async def test_only_the_steps_that_run_repository_code_get_docker(
    tmp_path: Path, phase: Phase, *, has_docker: bool
) -> None:
    runner = FakeRunner(good())
    where = volumes(tmp_path)
    await ContainerBackend(runner, volumes=where, docker=True).run(
        task(role=ROLES[phase], workdir=where.steps / "steps" / "a" / "repo", repo="acme/shop", work="w")
    )
    assert runner.requests[0].docker is has_docker


async def test_no_step_gets_docker_when_the_operator_did_not_turn_it_on(tmp_path: Path) -> None:
    runner = FakeRunner(good())
    where = volumes(tmp_path)
    await ContainerBackend(runner, volumes=where).run(
        task(role=ROLES[Phase.IMPLEMENT], workdir=where.steps / "steps" / "a" / "repo", repo="acme/shop", work="w")
    )
    assert runner.requests[0].docker is False
