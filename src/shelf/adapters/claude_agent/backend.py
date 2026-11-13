"""``AgentBackend`` over the Claude Agent SDK: each role is a sandboxed Claude Code session in the step's clone."""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import SandboxSettings

from shelf.domain.secrets import hidden_from_agents
from shelf.ports.agents import AgentTask

log = logging.getLogger(__name__)

AGENT_ENVIRONMENT = {"DO_NOT_TRACK": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
"""Telemetry off, and no memory carried from one step to the next: an agent starts each step from the repository."""


class AgentFailedError(RuntimeError):
    """The agent run ended in error."""

    def __init__(self, role: str, reason: str) -> None:
        """Say which role failed and why."""
        hint = (
            ". The agents run inside the worker container and need their own credential there, not the host's login: "
            "set CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`) or ANTHROPIC_API_KEY in deploy/.env, then run "
            "sh deploy/install.sh"
            if "not logged in" in reason.lower()
            else ""
        )
        super().__init__(f"{role} failed: {reason}{hint}")


def options_for(  # noqa: PLR0913 - one argument per setting the operator controls
    task: AgentTask,
    *,
    nested_sandbox: bool = False,
    sandbox: bool = True,
    cli_path: str | None = None,
    allowed_domains: tuple[str, ...] = (),
    bundles: tuple[Path, ...] = (),
) -> ClaudeAgentOptions:
    """The SDK options for ``task``: its own tools only, the sandbox on, bounded in turns and money.

    ``nested_sandbox`` selects the weaker sandbox mode that works inside a container (Docker). ``sandbox=False`` turns
    the sandbox off, for hosts where it cannot start: the container is then the only boundary around the agent.
    """
    return ClaudeAgentOptions(
        cwd=task.workdir,
        system_prompt={"type": "preset", "preset": "claude_code", "append": task.system_prompt},
        allowed_tools=list(task.role.tools),
        permission_mode="acceptEdits",
        max_turns=task.max_turns,
        max_budget_usd=task.max_budget_usd,
        model=task.model,
        cli_path=cli_path,
        env={**AGENT_ENVIRONMENT, **hidden_from_agents(os.environ), **task.env},
        # The skill bundles the operator bound to this role. Plugins for every agent come from the managed policy.
        plugins=[{"type": "local", "path": str(path)} for path in bundles],
        # The repository's own agent files (CLAUDE.md, skills, commands) are how it tells an agent its conventions.
        # Its hooks and MCP servers are code that would run in the worker: they are never loaded.
        setting_sources=["project"],
        settings=json.dumps({"disableAllHooks": True}),
        strict_mcp_config=True,
        sandbox=SandboxSettings(
            enabled=sandbox,
            autoAllowBashIfSandboxed=True,
            enableWeakerNestedSandbox=nested_sandbox,
            network={"allowedDomains": list(allowed_domains)},
        ),
    )


@dataclass(frozen=True, slots=True)
class ClaudeBackend:
    """Runs roles on the Claude Agent SDK. Credentials come from the environment of the worker."""

    nested_sandbox: bool = False
    sandbox: bool = True
    cli_path: str | None = None
    """A specific Claude Code executable to use instead of the one bundled with the SDK."""
    allowed_domains: tuple[str, ...] = ()
    """The sites a sandboxed command may reach: tool downloads and package registries."""
    catalog_dir: Path | None = None
    """Where the synced catalog is: one generated plugin per skill source."""
    bindings: Callable[[str], tuple[str, ...]] | None = None
    """The skill sources the operator bound to a role, read for every step so an edit applies at once."""

    def _bundles(self, role: str) -> tuple[Path, ...]:
        if self.catalog_dir is None or self.bindings is None:
            return ()
        found: list[Path] = []
        for name in self.bindings(role):
            path = self.catalog_dir / name
            if (path / ".claude-plugin" / "plugin.json").is_file():
                found.append(path)
            else:
                log.warning("role %s is bound to %s, which the catalog does not have: starting without it", role, name)
        return tuple(found)

    def options(self, task: AgentTask) -> ClaudeAgentOptions:
        """The SDK options for ``task``, with the bundles bound to its role."""
        return options_for(
            task,
            nested_sandbox=self.nested_sandbox,
            sandbox=self.sandbox,
            cli_path=self.cli_path,
            allowed_domains=self.allowed_domains,
            bundles=self._bundles(task.role.name),
        )

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the final answer."""
        answer = ""
        async for message in query(
            prompt=task.prompt,
            options=self.options(task),
        ):
            if isinstance(message, ResultMessage):
                if message.is_error:
                    raise AgentFailedError(task.role.name, message.result or message.subtype)
                answer = message.result or ""
        return answer
