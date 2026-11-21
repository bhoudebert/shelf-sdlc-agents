"""Running one of a repository's check commands somewhere other than the worker's own shell."""

from pathlib import Path
from typing import Protocol

from shelf.ports.workspace import CheckResult


class CommandRunner(Protocol):
    """Runs a command of a repository's ``checks`` in its clone and says how it ended."""

    async def run(self, repo: str, workdir: Path, command: str) -> CheckResult:
        """The command's exit code and the end of its output; a command that could not run is a failed result."""
        ...
