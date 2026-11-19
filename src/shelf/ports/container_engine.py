"""The container engine the runner drives (Docker or Podman, over its socket). Only what the runner needs."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Owned:
    """A container the runner made, as found again after a restart."""

    id: str
    labels: Mapping[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True, slots=True)
class Finished:
    """How a container ended."""

    code: int
    oom: bool = False


class EngineError(RuntimeError):
    """The engine refused or could not be reached. The message never holds a request body: it may carry a secret."""


class ContainerEngine(Protocol):
    """Create, start, read, stop and remove containers. The runner is the only caller."""

    async def create(self, spec: Mapping[str, Any], name: str) -> str:
        """Create a container from the engine's own request body and return its id."""
        ...

    async def put_file(self, container: str, directory: str, name: str, data: bytes) -> None:
        """Write one file, readable by the step's user only, into a directory of a container not yet started."""
        ...

    async def start(self, container: str) -> None:
        """Start a created container."""
        ...

    def stdout(self, container: str) -> AsyncIterator[bytes]:
        """The container's standard output from its first byte, following until it ends. Standard error is not here."""
        ...

    async def wait(self, container: str) -> Finished:
        """Wait until the container has stopped and say how."""
        ...

    async def kill(self, container: str) -> None:
        """Stop the container at once. A container that is already gone is not an error."""
        ...

    async def remove(self, container: str) -> None:
        """Remove the container and its anonymous volumes. A container that is already gone is not an error."""
        ...

    async def owned(self) -> list[Owned]:
        """Every container that carries the runner's label. Raises ``EngineError`` when the engine cannot be read."""
        ...
