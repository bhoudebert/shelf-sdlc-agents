"""Run steps in containers, one record per key: stream the lines, write the ``exit`` line, remember the result.

The record outlives the caller's connection: a worker that restarted asks again with the same key and reads the lines
from where it stopped. The ``exit`` line is written here, after the container is gone, never by the step.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Final

from shelf.domain.stepspec import TASK_DIR, TASK_FILE, RunnerRules, StepAsk, container_spec
from shelf.domain.stepstream import Exit, Ping, encode
from shelf.ports.container_engine import ContainerEngine, EngineError

log = logging.getLogger(__name__)

PING_EVERY: Final = 3.0
RETENTION: Final = 24 * 3600.0
GRACE: Final = 60
"""Seconds after its deadline that a container is still expected to exist, so the reaper never races the runner."""
MAX_OUTPUT: Final = 32 * 1024 * 1024
"""Bytes of output a step may write. A step that writes more is stopped."""


@dataclass(eq=False)
class StepRecord:
    """One step: its request, the lines it wrote, and how it ended."""

    ask: StepAsk
    started: float
    lines: list[str] = field(default_factory=list[str])
    size: int = 0
    done: bool = False
    exit: Exit | None = None
    finished: float = 0.0
    container: str = ""
    stopped: bool = False
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None


def _news(record: StepRecord, seen: int) -> Callable[[], bool]:
    return lambda: seen < len(record.lines) or record.done


class StepService:
    """Start, follow, stop and forget steps. The clock and the ping interval are arguments so a test controls them."""

    def __init__(
        self,
        engine: ContainerEngine,
        rules: RunnerRules,
        *,
        clock: Callable[[], float] = time.time,
        ping_every: float = PING_EVERY,
    ) -> None:
        """Run steps on ``engine`` under ``rules``."""
        self._engine = engine
        self._rules = rules
        self._clock = clock
        self._ping_every = ping_every
        self._steps: dict[str, StepRecord] = {}

    def known(self, key: str) -> StepRecord | None:
        """The record of a step this runner started, or ``None``."""
        return self._steps.get(key)

    def start(self, ask: StepAsk) -> StepRecord:
        """The step for ``ask.key``: the one already there, or a new one running in the background."""
        self._forget_old()
        if (record := self._steps.get(ask.key)) is not None:
            return record
        record = StepRecord(ask, started=self._clock())
        self._steps[ask.key] = record
        record.task = asyncio.create_task(self._drive(record))
        return record

    async def follow(self, record: StepRecord, cursor: int = 0) -> AsyncIterator[str]:
        """The lines of a step from ``cursor``, then pings while it is quiet, until its last line."""
        seen = max(cursor, 0)
        while True:
            while seen < len(record.lines):
                yield record.lines[seen]
                seen += 1
            if record.done:
                return
            async with record.changed:
                try:
                    await asyncio.wait_for(record.changed.wait_for(_news(record, seen)), self._ping_every)
                except TimeoutError:
                    yield encode(Ping())

    async def stop(self, record: StepRecord) -> None:
        """Stop a running step; its stream ends with ``killed``. A finished step is left as it is."""
        if record.done:
            return
        record.stopped = True
        if record.container:
            await self._engine.kill(record.container)

    async def reap(self) -> int:
        """Remove the containers that carry the runner's label and are past their time; return how many.

        Raises ``EngineError`` when the engine cannot be read: the runner then does not start.
        """
        gone = 0
        now = self._clock()
        for found in await self._engine.owned():
            expires = found.labels.get("shelf.expires", "")
            if expires.isdigit() and int(expires) < now:
                await self._engine.kill(found.id)
                await self._engine.remove(found.id)
                gone += 1
        self._forget_old()
        return gone

    def _forget_old(self) -> None:
        now = self._clock()
        for key in [k for k, r in self._steps.items() if r.done and now - r.finished > RETENTION]:
            del self._steps[key]

    async def _publish(self, record: StepRecord, line: str) -> None:
        async with record.changed:
            record.lines.append(line)
            record.size += len(line)
            record.changed.notify_all()

    async def _drive(self, record: StepRecord) -> None:
        ask = record.ask
        try:
            async with asyncio.timeout(ask.limits.seconds):
                code, reason = await self._execute(record)
        except TimeoutError:
            code, reason = -1, "timeout"
            await self._discard(record)
        except EngineError as error:
            log.warning("step %s: %s", ask.key[:60], error)
            code, reason = -1, "engine"
            await self._discard(record)
        except Exception:
            log.exception("step %s failed in the runner", ask.key[:60])
            code, reason = -1, "engine"
            await self._discard(record)
        record.exit = Exit(code, reason)
        record.finished = self._clock()
        await self._publish(record, encode(record.exit))
        async with record.changed:
            record.done = True
            record.changed.notify_all()

    async def _discard(self, record: StepRecord) -> None:
        if not record.container:
            return
        try:
            await self._engine.kill(record.container)
            await self._engine.remove(record.container)
        except EngineError as error:
            log.warning("step %s could not be removed: %s", record.ask.key[:60], error)

    async def _execute(self, record: StepRecord) -> tuple[int, str]:
        ask = record.ask
        name = "shelf-step-" + hashlib.sha256(ask.key.encode()).hexdigest()[:16]
        expires = int(self._clock()) + ask.limits.seconds + GRACE
        await self._engine.remove(name)
        record.container = await self._engine.create(container_spec(ask, self._rules, expires=expires), name)
        task: dict[str, Any] = dict(ask.input)
        await self._engine.put_file(record.container, TASK_DIR, TASK_FILE, json.dumps(task).encode())
        await self._engine.start(record.container)
        pending = ""
        async for chunk in self._engine.stdout(record.container):
            pending += chunk.decode("utf-8", errors="replace")
            *whole, pending = pending.split("\n")
            for line in whole:
                if line.strip():
                    await self._publish(record, line)
            if record.size > MAX_OUTPUT:
                record.stopped = True
                await self._engine.kill(record.container)
                break
        if pending.strip():
            await self._publish(record, pending)
        finished = await self._engine.wait(record.container)
        await self._engine.remove(record.container)
        reason = "oom" if finished.oom else "killed" if record.stopped else ""
        return finished.code, reason
