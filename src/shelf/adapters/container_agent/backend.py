"""``AgentBackend`` over the runner service: each step is a container, and what it does comes back as lines."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from fnmatch import fnmatchcase
from pathlib import Path
from uuid import uuid4

from shelf.domain.roles import RUNS_CODE
from shelf.domain.runlog import redact
from shelf.domain.stepfail import explain_model_failure
from shelf.domain.stepspec import ENV_ALLOWED, TOOLS
from shelf.domain.stepstream import StepStream, StreamError
from shelf.domain.toolchain import repository_folder
from shelf.ports.agents import AgentTask, RunSink, go_on_after_turns
from shelf.ports.step_runner import StepRequest, StepRunner, StepSettings, task_input

log = logging.getLogger(__name__)


class StepFailedError(RuntimeError):
    """A step in a container ended in error, or did not end properly."""

    def __init__(self, role: str, reason: str) -> None:
        """Say which role failed and why."""
        super().__init__(f"{role} failed: {reason}")


def _new_key() -> str:
    return uuid4().hex


def _note(stream: StepStream, sink: RunSink) -> None:
    """What the lines said, in the record of the run: the same fields the sandbox path fills."""
    sink.tools.extend(stream.tools)
    done = stream.result
    if done is None:
        return
    sink.usage = done.usage
    sink.session_id = done.session
    sink.subtype = done.subtype
    sink.stop_reason = done.stop_reason
    sink.terminal_reason = done.terminal_reason
    sink.api_error_status = done.api_error_status
    sink.errors = list(done.errors)
    sink.denials.extend(done.denials)


@dataclass(frozen=True, slots=True)
class Volumes:
    """The three volumes the worker shares with the runner, as the worker sees them."""

    steps: Path
    """Holds ``steps/<name>/repo``, the clones: the worker's workspaces are made under ``steps/``."""
    tools: Path
    """Holds ``home/<owner>__<name>``, the repositories' homes: the worker's own tool set-up writes there too."""
    sessions: Path
    """Holds ``work/<id>``, the sessions of each work."""

    def clone_of(self, workdir: Path) -> str:
        """The clone's place in the clones volume, which is all the request says of it."""
        try:
            return workdir.relative_to(self.steps).as_posix()
        except ValueError:
            reason = "the step's clone is not in the shared clones volume (SHELF_STEPS_DIR)"
            role = "step"
            raise StepFailedError(role, reason) from None

    def prepare(self, repo: str, work: str) -> None:
        """Make the folders the runner mounts: it never makes one, and a missing one stops the container."""
        home = self.tools / repository_folder(repo)
        for folder in TOOLS:
            (home / folder).mkdir(parents=True, exist_ok=True)
        if work:
            (self.sessions / "work" / work).mkdir(parents=True, exist_ok=True)


def sendable(env: Mapping[str, str]) -> dict[str, str]:
    """The variables the runner accepts. The worker's own ``HOME``, ``PATH`` and ``MISE_*`` stay in the worker."""
    return {name: value for name, value in env.items() if any(fnmatchcase(name, p) for p in ENV_ALLOWED)}


@dataclass(frozen=True, slots=True)
class ContainerBackend:
    """Runs roles in a container per step: the worker holds no agent process, it asks the runner and reads lines."""

    runner: StepRunner
    web: bool = False
    """Whether agents may read the web (``SHELF_WEB``)."""
    allowed_domains: tuple[str, ...] = ()
    bindings: Callable[[str], tuple[str, ...]] | None = None
    """The skill sources the operator bound to a role, read for every step so an edit applies at once."""
    extra_domains: Callable[[], tuple[str, ...]] | None = None
    """The sites an administrator added from the page, read for every step so a change applies at once."""
    volumes: Volumes | None = None
    """Where the clones, tools and sessions are; without it the request names none (a test with a fake runner)."""
    docker: bool = False
    """Each step that runs repository code asks the runner for a Docker daemon of its own (decision 0020)."""
    model_env: Mapping[str, str] = field(default_factory=dict[str, str], repr=False)
    """The model credential, sent with every step: a container inherits nothing from the worker."""
    new_key: Callable[[], str] = _new_key
    """A key for a step with none of its own yet; a later stage passes the workflow's, so a retry re-attaches."""

    def _settings(self, task: AgentTask) -> StepSettings:
        added: tuple[str, ...] = ()
        if self.extra_domains is not None:
            try:
                added = tuple(self.extra_domains())
            except Exception:  # noqa: BLE001 - an unreadable store never stops a step: the configured sites remain
                log.warning("could not read the sites added from the page: starting with the configured ones")
        bundles = self.bindings(task.role.name) if self.bindings is not None else ()
        return StepSettings(
            web=self.web,
            allowed_domains=tuple(dict.fromkeys((*self.allowed_domains, *added))),
            bundles=tuple(bundles),
        )

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the final answer; a session that cannot be continued starts again from scratch."""
        if task.resume:
            try:
                return await go_on_after_turns(self._run_once, task)
            except Exception as error:  # noqa: BLE001 - whatever stopped the continuation, the step must still run
                log.warning("could not continue the session of %s (%s): starting again", task.role.name, error)
                if task.sink is not None:
                    task.sink.fell_back = True
                task = replace(task, resume="", prompt=task.fallback_prompt or task.prompt)
        return await go_on_after_turns(self._run_once, task)

    def _request(self, task: AgentTask) -> StepRequest:
        """What to ask the runner for ``task``: its clone, repository, session and tools mode, their folders made."""
        key, env, given = (
            self.new_key(),
            sendable({**self.model_env, **task.env}),
            task_input(task, self._settings(task)),
        )
        if self.volumes is None:
            return StepRequest(key=key, env=env, input=given)
        self.volumes.prepare(task.repo, task.work)
        return StepRequest(
            key=key,
            repo=task.repo,
            clone=self.volumes.clone_of(task.workdir),
            session=f"work/{task.work}" if task.work else "",
            tools_readonly=task.read_only_tools,
            env=env,
            input=given,
            docker=self.docker and task.role.name in RUNS_CODE,
        )

    async def _run_once(self, task: AgentTask) -> str:
        request = self._request(task)
        stream = StepStream()
        reason = ""
        try:
            async for line in self.runner.run(request):
                stream.feed(line)
        except StreamError as error:
            reason = str(error)
        if task.sink is not None:
            _note(stream, task.sink)
        done = stream.result
        if not reason:
            reason = (done.result or done.subtype) if done is not None and done.is_error else stream.failure()
            reason = explain_model_failure(reason)
        if reason:
            if task.sink is not None and not task.sink.error:
                task.sink.error = redact(" ".join(reason.split()))[:400]
            raise StepFailedError(task.role.name, reason)
        return done.result if done is not None else ""
