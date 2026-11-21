"""``shelf-check``: what runs inside a ``check`` step's container. It runs one shell command and writes two lines.

The command is one of the repository's own ``checks``, in the clone at ``/work``, with the step's own home and tool
shims. The worker reads the same stream as for an agent (``shelf.domain.stepstream``): ``hello``, then one ``check``
line with the command's exit code and the end of its output. The step itself ends well whatever the command did: a
failing command is a result, not a failure of the step.
"""

import asyncio
import json
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


async def run_check(command: str, workdir: Path, emit: Callable[[Event], None]) -> None:
    """Run ``command`` in ``workdir``, say hello, and emit its exit code and the end of its output."""
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
    emit(Check(code, kept.decode(errors="replace")[-KEPT:]))


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
