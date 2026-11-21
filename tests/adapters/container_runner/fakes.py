"""A fake container engine: plays a script of output and remembers every call."""

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

from shelf.ports.container_engine import EngineError, Finished, Owned


class FakeEngine:
    """Stands in for Docker: no daemon, no socket."""

    def __init__(  # noqa: PLR0913
        self,
        chunks: list[bytes] | None = None,
        *,
        finished: Finished | None = None,
        hang: bool = False,
        fail_create: bool = False,
        existing: list[Owned] | None = None,
        unreadable: bool = False,
        runtimes: list[str] | None = None,
    ) -> None:
        self.chunks = chunks or []
        self.finished = finished or Finished(0)
        self.hang = hang
        self.fail_create = fail_create
        self.existing = existing or []
        self.unreadable = unreadable
        self.runtimes_listed = runtimes if runtimes is not None else ["runc"]
        self.created: list[tuple[Mapping[str, Any], str]] = []
        self.files: list[tuple[str, str, str, bytes]] = []
        self.started: list[str] = []
        self.killed: list[str] = []
        self.removed: list[str] = []
        self._stopped = asyncio.Event()

    async def runtimes(self) -> list[str]:
        return self.runtimes_listed

    async def create(self, spec: Mapping[str, Any], name: str) -> str:
        if self.fail_create:
            message = "the container engine answered 500 to POST containers"
            raise EngineError(message)
        self.created.append((spec, name))
        return f"id-{len(self.created)}"

    async def put_file(self, container: str, directory: str, name: str, data: bytes) -> None:
        self.files.append((container, directory, name, data))

    async def start(self, container: str) -> None:
        self.started.append(container)

    async def stdout(self, container: str) -> AsyncIterator[bytes]:
        del container
        for chunk in self.chunks:
            yield chunk
        if self.hang:
            await self._stopped.wait()

    async def wait(self, container: str) -> Finished:
        del container
        return self.finished

    async def kill(self, container: str) -> None:
        self.killed.append(container)
        self._stopped.set()

    async def remove(self, container: str) -> None:
        self.removed.append(container)

    async def owned(self) -> list[Owned]:
        if self.unreadable:
            message = "the container engine could not be reached: ConnectError"
            raise EngineError(message)
        return self.existing
