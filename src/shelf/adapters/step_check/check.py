"""``shelf-check``: what runs inside a ``check`` step's container. It runs one shell command and writes two lines.

The command is one of the repository's own ``checks``, in the clone at ``/work``, with the step's own home and tool
shims. The worker reads the same stream as for an agent (``shelf.domain.stepstream``): ``hello``, then one ``check``
line with the command's exit code and the end of its output. The step itself ends well whatever the command did: a
failing command is a result, not a failure of the step.
"""

import asyncio
import json
import re
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final, cast

from shelf.domain.stepstream import PROTOCOL, Check, Event, Hello, encode

WORKDIR: Final = Path("/work")
"""Where the runner mounts the clone."""
KEPT: Final = 20_000
"""How much of the end of the output is kept: the worker shows the last 4000 characters, with room to spare."""
CHUNK: Final = 65_536
DOCKER_TIMEOUT: Final = 15.0
"""How long one question to the step's daemon may take: a check that failed must still end."""
LOG_LINES: Final = 40
CONTAINERS_SHOWN: Final = 4
CONTAINER_CHARS: Final = 2_500
PROBES_SHOWN: Final = 3
PROBE_CHARS: Final = 300
PROGRESS: Final = re.compile(r"^\s*([0-9a-f]{12}) (Extracting|Downloading)\b")
"""One line of an image pull: a layer's id and what it is doing. Each repeats with new numbers, hundreds of times."""


def collapse_progress(text: str) -> str:
    """``text`` with the lines of a layer's pull progress that follow each other cut to the last: only the end matters.

    Other lines, and layers that take turns, are left as they are.
    """
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        found = PROGRESS.match(line)
        previous = PROGRESS.match(kept[-1]) if kept else None
        if found and previous and found.groups() == previous.groups():
            kept[-1] = line
        else:
            kept.append(line)
    return "".join(kept)


async def _ask_docker(*args: str, limit: float) -> str | None:
    """What ``docker <args>`` printed, or ``None`` when it failed, is not there or took too long."""
    try:
        process = await asyncio.create_subprocess_exec(
            "docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except OSError:
        return None
    try:
        async with asyncio.timeout(limit):
            output, _ = await process.communicate()
    except TimeoutError:
        process.kill()
        await process.wait()
        return None
    return output.decode(errors="replace") if process.returncode == 0 else None


def probes_of(health: str | None) -> str:
    """The last probes of a healthcheck, as ``docker inspect`` reports them: exit code and what each printed."""
    try:
        parsed = json.loads(health or "null")
    except ValueError:
        return ""
    log = cast("dict[str, Any]", parsed).get("Log") if isinstance(parsed, dict) else None
    if not isinstance(log, list) or not log:
        return ""
    lines = ["the healthcheck's last probes:"]
    for probe in cast("list[Any]", log)[-PROBES_SHOWN:]:
        if not isinstance(probe, dict):
            continue
        entry = cast("dict[str, Any]", probe)
        printed = " ".join(str(entry.get("Output", "")).split())[:PROBE_CHARS] or "(it printed nothing)"
        lines.append(f"  exit code {entry.get('ExitCode')}: {printed}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _is_well(status: str) -> bool:
    return status.startswith("Up") and "unhealthy" not in status and "starting" not in status


async def containers_said(limit: float) -> str:
    """The state of the step's containers and the end of the log of those not well; empty when there are none."""
    if shutil.which("docker") is None or await _ask_docker("info", limit=limit) is None:
        return ""
    listed = await _ask_docker("ps", "-a", "--format", "{{.Names}}\t{{.Status}}", limit=limit)
    rows = [line.split("\t", 1) for line in (listed or "").splitlines() if "\t" in line]
    if not rows:
        return ""
    sections = ["", "--- the step's containers (docker ps -a) ---", *(f"{name}: {status}" for name, status in rows)]
    for name, status in [row for row in rows if not _is_well(row[1])][:CONTAINERS_SHOWN]:
        log = await _ask_docker("logs", "--tail", str(LOG_LINES), name, limit=limit)
        sections += [
            "",
            f"--- {name} ({status}): the last lines of its log ---",
            (log or "(no log)")[-CONTAINER_CHARS:].rstrip(),
        ]
        health = await _ask_docker("inspect", "--format", "{{json .State.Health}}", name, limit=limit)
        if probes := probes_of(health):
            sections += ["", probes]
    return "\n".join(sections) + "\n"


async def run_check(
    command: str, workdir: Path, emit: Callable[[Event], None], *, docker_timeout: float = DOCKER_TIMEOUT
) -> None:
    """Run ``command`` in ``workdir``, say hello, and emit its exit code and the end of its output.

    A command that failed in a step with a Docker daemon is followed by what the step's containers said.
    """
    emit(Hello(PROTOCOL))
    # The commands are the repository's own checks, from its reviewed .shelf/config.toml: a shell is the point.
    process = await asyncio.create_subprocess_shell(
        command, cwd=workdir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    assert process.stdout is not None  # noqa: S101 - the pipe was asked for above
    kept = b""
    while chunk := await process.stdout.read(CHUNK):
        kept = (kept + chunk)[-KEPT * 4 :]  # bytes: a character takes up to four
    code = await process.wait()
    output = collapse_progress(kept.decode(errors="replace"))
    extra = await containers_said(docker_timeout) if code != 0 else ""
    emit(Check(code, (output[-(KEPT - len(extra)) :] if len(extra) < KEPT else "") + extra[-KEPT:]))


def _write(event: Event) -> None:
    sys.stdout.write(encode(event) + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None, workdir: Path = WORKDIR) -> int:
    """Read the task (``{"command": ...}``) from the file named first, run it, write the lines."""
    args = sys.argv[1:] if argv is None else argv
    try:
        task = json.loads(Path(args[0]).read_text(encoding="utf-8")) if args else json.loads(sys.stdin.read())
    except (OSError, ValueError):
        sys.stderr.write("shelf-check stopped: the task could not be read\n")
        return 1
    command = cast("dict[str, Any]", task).get("command") if isinstance(task, dict) else None
    if not isinstance(command, str) or not command.strip():
        sys.stderr.write("shelf-check stopped: the task has no command\n")
        return 1
    asyncio.run(run_check(command, workdir, _write))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
