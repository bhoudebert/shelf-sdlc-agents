"""Read the guard's audit log by asking the ``warden`` binary, the only way this code reaches it."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from shelf.domain.guard import GuardReport
from shelf.domain.result import Err, Ok, Result

TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class WardenReader:
    """Runs ``warden report --json`` and ``warden audit verify``, which read the log and never change it."""

    binary: str = "warden"

    async def report(self) -> Result[GuardReport, str]:
        """The counts of the log, or a sentence saying why they could not be read."""
        try:
            code, out = await self._run("report", "--json")
            if code != 0:
                return Err("the guard could not read its log")
            data: dict[str, Any] = json.loads(out)
            verified, _ = await self._run("audit", "verify")
            return Ok(
                GuardReport(
                    calls=int(data["calls"]),
                    stopped=int(data["would_stop"]),
                    redactions=sum(int(count) for count in data["redactions"].values()),
                    chain_intact=verified == 0,
                    categories={str(name): int(count) for name, count in data["by_category"].items()},
                )
            )
        except FileNotFoundError:
            return Err("the guard is not installed")
        except (TimeoutError, OSError):
            return Err("the guard did not answer")
        except (ValueError, KeyError, TypeError, AttributeError):
            return Err("the guard answered in a way this version does not understand")

    async def _run(self, *args: str) -> tuple[int, str]:
        process = await asyncio.create_subprocess_exec(
            self.binary, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        try:
            out, _ = await asyncio.wait_for(process.communicate(), TIMEOUT_SECONDS)
        except TimeoutError:
            process.kill()
            raise
        return process.returncode or 0, out.decode()
