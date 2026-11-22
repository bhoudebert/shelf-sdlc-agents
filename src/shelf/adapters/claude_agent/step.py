"""``shelf-step``: what runs inside a step's container. It reads the task, runs the agent and writes the lines.

The container is the boundary, so the SDK's own sandbox is off here. The worker never runs this code and never sees the
agent's messages: it reads what this writes (``shelf.domain.stepstream``).
"""

import asyncio
import json
import os
import socket
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from pathlib import Path
from urllib.parse import urlparse

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolResultBlock, ToolUseBlock, UserMessage, query

from shelf.adapters.claude_agent.backend import denial_line, options_for, usage_of
from shelf.domain.runlog import redact, result_note, tool_summary
from shelf.domain.stepenv import JDKS, jdk_environment
from shelf.domain.stepfail import unresolvable
from shelf.domain.stepstream import PROTOCOL, Event, Hello, Result, Tool, ToolResult, encode
from shelf.ports.agents import AgentTask
from shelf.ports.step_runner import StepSettings, task_from_input

WORKDIR = Path("/work")
"""Where the runner mounts the clone."""
CATALOG = Path("/opt/shelf/catalog")
"""The skill bundles baked into the image, one folder per source."""


def _denials(message: ResultMessage) -> tuple[str, ...]:
    return tuple(denial_line(denied) for denied in message.permission_denials or [])


def events_of(message: object) -> list[Event]:
    """The lines an SDK message becomes: a tool call, how one ended, or the result of the run."""
    found: list[Event] = []
    if isinstance(message, AssistantMessage):
        found.extend(
            Tool(block.id, block.name, tool_summary(block.name, block.input))
            for block in message.content
            if isinstance(block, ToolUseBlock)
        )
    elif isinstance(message, UserMessage) and isinstance(message.content, list):
        found.extend(
            ToolResult(block.tool_use_id, error=True, note=result_note(block.content))
            for block in message.content
            if isinstance(block, ToolResultBlock) and block.is_error
        )
    elif isinstance(message, ResultMessage):
        found.append(
            Result(
                is_error=bool(message.is_error),
                result=message.result or "",
                session=message.session_id or "",
                usage=usage_of(message),
                subtype=message.subtype or "",
                stop_reason=message.stop_reason or "",
                terminal_reason=message.terminal_reason or "",
                api_error_status=message.api_error_status,
                errors=tuple(redact(str(error))[:300] for error in (message.errors or [])),
                denials=_denials(message),
            )
        )
    return found


async def run_step(
    task: AgentTask,
    settings: StepSettings,
    emit: Callable[[Event], None],
    messages: AsyncIterator[object] | None = None,
) -> None:
    """Run ``task`` and ``emit`` every event. ``messages`` replaces the SDK in tests."""
    emit(Hello(PROTOCOL))
    if messages is None:
        options = options_for(
            task,
            sandbox=False,
            allowed_domains=settings.allowed_domains,
            bundles=tuple(CATALOG / name for name in settings.bundles if (CATALOG / name).is_dir()),
            web=settings.web,
        )
        messages = query(prompt=task.prompt, options=options)
    async for message in messages:
        for event in events_of(message):
            emit(event)


PROXIES = ("HTTPS_PROXY", "ALL_PROXY", "https_proxy", "all_proxy")
"""Where a step that reaches the network through a proxy says so: the proxy resolves, not the step."""


def preflight(environ: Mapping[str, str]) -> str | None:
    """Why the agent cannot reach the model, found before it starts (it would retry for minutes), or ``None``.

    The host looked up is the one of ``ANTHROPIC_BASE_URL``, else ``api.anthropic.com``; nothing is looked up behind
    a proxy.
    """
    if any(environ.get(name) for name in PROXIES):
        return None
    base = environ.get("ANTHROPIC_BASE_URL", "")
    host = (urlparse(base).hostname if base else None) or "api.anthropic.com"
    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror as error:
        return unresolvable(host, error.strerror or str(error))
    except OSError:
        return None
    return None


def _write(event: Event) -> None:
    sys.stdout.write(encode(event) + "\n")
    sys.stdout.flush()


def installed_jdks(home: Path) -> list[str]:
    """The JDKs mise installed in ``home``: one folder per version, never a link (``latest``)."""
    try:
        return sorted(p.name for p in (home / JDKS).iterdir() if p.is_dir() and not p.is_symlink())
    except OSError:
        return []


def main(argv: list[str] | None = None, home: Path | None = None) -> int:
    """Read the task as JSON from the file named first (or standard input), run it, write the lines."""
    args = sys.argv[1:] if argv is None else argv
    raw = Path(args[0]).read_text(encoding="utf-8") if args else sys.stdin.read()
    task, settings = task_from_input(json.loads(raw), WORKDIR)
    base = home if home is not None else Path(os.environ.get("HOME", "/home/step"))
    os.environ.update(jdk_environment(os.environ, str(base), installed_jdks(base)))
    if (problem := preflight(os.environ)) is not None:
        _write(Hello(PROTOCOL))
        _write(Result(is_error=True, result=problem, subtype="preflight"))
        return 0
    try:
        asyncio.run(run_step(task, settings, _write))
    except Exception as error:  # noqa: BLE001 - the agent's CLI ending badly must not print a traceback that may hold a secret
        sys.stderr.write(f"shelf-step stopped: {type(error).__name__}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
