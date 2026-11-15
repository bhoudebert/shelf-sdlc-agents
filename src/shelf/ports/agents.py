"""The agent runtime: run one role on a working copy with a budget."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from shelf.domain.roles import AgentRole
from shelf.domain.usage import Usage


@dataclass(eq=False)
class RunSink:
    """Where a backend puts what it knows about a run: what it used, and the session it ran in."""

    usage: Usage | None = None
    session_id: str = ""
    """The agent's session, so that a later run can continue it."""


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


class AgentBackend(Protocol):
    """Run a role and return its final answer. The backend decides how (Claude Agent SDK, another harness)."""

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the agent's final text. Raises when the run fails."""
        ...
