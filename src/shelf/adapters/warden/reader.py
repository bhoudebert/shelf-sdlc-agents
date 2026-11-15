"""Read the guard's audit log by asking the ``warden`` binary, the only way this code reaches it."""

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from shelf.domain.guard import GuardReport, StoppedCall
from shelf.domain.result import Err, Ok, Result

TIMEOUT_SECONDS = 10



def _stopped(call: dict[str, Any]) -> StoppedCall:
    return StoppedCall(
        at=str(call["at"]),
        agent=str(call["agent"]),
        session=str(call["session"]),
        kind=str(call["kind"]),
        decision=str(call["decision"]),
        intended=str(call.get("intended", "")),
        categories=tuple(str(name) for name in call["categories"]),
        reason=str(call["reason"]),
        summary=str(call["summary"]),
    )


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
                    recent=tuple(_stopped(call) for call in data.get("recent", [])),
                    web_hosts={str(host): int(count) for host, count in data.get("web_hosts", {}).items()},
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
