"""The agent runtime: run one role on a working copy with a budget."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from shelf.domain.roles import AgentRole
from shelf.domain.runlog import ToolEvent
from shelf.domain.usage import Usage


@dataclass(eq=False)
class RunSink:
    """Where a backend puts what it knows about a run: what it used, and the session it ran in."""

    usage: Usage | None = None
    session_id: str = ""
    """The agent's session, so that a later run can continue it."""
    tools: list[ToolEvent] = field(default_factory=list[ToolEvent])
    """Every tool call the agent made, in order, shortened and redacted."""
    denials: list[str] = field(default_factory=list[str])
    """The tool calls its permissions refused."""
    subtype: str = ""
    stop_reason: str = ""
    terminal_reason: str = ""
    api_error_status: int | None = None
    errors: list[str] = field(default_factory=list[str])
    fell_back: bool = False
    """Whether a session that could not be continued was started again from the whole task."""
    error: str = ""


@dataclass(frozen=True, slots=True)
class AgentTask:
    """What to ask an agent, where, and how much it may spend."""

    role: AgentRole
    system_prompt: str
    prompt: str
    workdir: Path
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    max_turns: int = 40
    max_budget_usd: float | None = None
    model: str | None = None
    sink: RunSink | None = field(default=None, compare=False)
    """Filled with what the run used and the session it ran in, when the backend can say."""
    resume: str = ""
    """The session of an earlier run to continue; empty to start a new one."""
    fallback_prompt: str = ""
    """What to ask instead, from the start, when the session to continue cannot be continued."""
    repo: str = ""
    """``owner/name`` of the repository, for a backend that gives each repository its own tools."""
    work: str = ""
    """The work's id, for a backend that keeps a work's sessions together."""
    read_only_tools: bool = False
    """The role reads the repository's tools and caches but must not change them (a reviewer)."""


OUT_OF_TURNS = "error_max_turns"
"""How a run says it used all its turns."""

GO_ON = (
    "You used all your turns before you finished. Your work so far is kept in the working directory. Go on from where "
    "you stopped, do what is left of the task, and end with the answer the task asks for."
)


async def go_on_after_turns(run: Callable[[AgentTask], Awaitable[str]], task: AgentTask) -> str:
    """Run ``task``; when it uses all its turns in a session, ask that session once to go on, and add up the use.

    A second run that ends badly too raises, as any failed run does.
    """
    try:
        return await run(task)
    except Exception:
        sink = task.sink
        if sink is None or sink.subtype != OUT_OF_TURNS or not sink.session_id:
            raise
        first = sink.usage
        sink.error = ""
        try:
            return await run(replace(task, resume=sink.session_id, prompt=GO_ON, fallback_prompt=""))
        finally:
            if first is not None and sink.usage is not None:
                sink.usage = first + sink.usage


class AgentBackend(Protocol):
    """Run a role and return its final answer. The backend decides how (Claude Agent SDK, another harness)."""

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the agent's final text. Raises when the run fails."""
        ...
