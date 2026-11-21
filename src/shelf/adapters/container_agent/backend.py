"""``AgentBackend`` over the runner service: each step is a container, and what it does comes back as lines."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from uuid import uuid4

from shelf.domain.runlog import redact
from shelf.domain.stepstream import StepStream, StreamError
from shelf.ports.agents import AgentTask, RunSink
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
                return await self._run_once(task)
            except Exception as error:  # noqa: BLE001 - whatever stopped the continuation, the step must still run
                log.warning("could not continue the session of %s (%s): starting again", task.role.name, error)
                if task.sink is not None:
                    task.sink.fell_back = True
                task = replace(task, resume="", prompt=task.fallback_prompt or task.prompt)
        return await self._run_once(task)

    async def _run_once(self, task: AgentTask) -> str:
        request = StepRequest(key=self.new_key(), env=dict(task.env), input=task_input(task, self._settings(task)))
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
        if reason:
            if task.sink is not None and not task.sink.error:
                task.sink.error = redact(" ".join(reason.split()))[:400]
            raise StepFailedError(task.role.name, reason)
        return done.result if done is not None else ""
