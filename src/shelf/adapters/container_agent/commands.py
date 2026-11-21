"""A repository's check command, run as a ``check`` step in a container of its own (decision 0019, stage 3b).

The worker holds no shell for it: it asks the runner, with the clone and the repository's tools and no credential, and
reads the one ``check`` line the step writes. A step that did not end properly is a failed check that says why, never a
pass.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from shelf.adapters.container_agent.backend import StepFailedError, Volumes
from shelf.adapters.container_agent.client import RunnerError
from shelf.domain.runlog import redact
from shelf.domain.stepstream import StepStream, StreamError
from shelf.ports.step_runner import StepRequest, StepRunner
from shelf.ports.workspace import CheckResult


def _new_key() -> str:
    return uuid4().hex


COULD_NOT_RUN = -1
"""The exit code of a check that did not run to its end: not the command's own, and never zero."""


def _did_not_run(command: str, reason: str) -> CheckResult:
    return CheckResult(
        command, COULD_NOT_RUN, f"the check did not run to its end: {redact(' '.join(reason.split()))[:400]}"
    )


@dataclass(frozen=True, slots=True)
class ContainerCommands:
    """``CommandRunner`` over the runner service."""

    runner: StepRunner
    volumes: Volumes
    docker: bool = False
    """Each check asks for a Docker daemon of its own (decision 0020), like the developer's step."""
    new_key: Callable[[], str] = _new_key

    async def run(self, repo: str, workdir: Path, command: str) -> CheckResult:
        """Run ``command`` in the clone as a check step."""
        try:
            clone = self.volumes.clone_of(workdir)
        except StepFailedError as error:
            return _did_not_run(command, str(error))
        self.volumes.prepare(repo, "")
        request = StepRequest(
            key=self.new_key(),
            kind="check",
            repo=repo,
            clone=clone,
            input={"command": command},
            docker=self.docker,
        )
        stream = StepStream()
        try:
            async for line in self.runner.run(request):
                stream.feed(line)
        except (StreamError, RunnerError) as error:
            return _did_not_run(command, str(error))
        if reason := stream.failure():
            return _did_not_run(command, reason)
        if stream.check is None:
            return _did_not_run(command, "the step ended without reporting the command")
        return CheckResult(command, stream.check.code, stream.check.output)
