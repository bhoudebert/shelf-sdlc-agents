"""``AgentBackend`` over the Claude Agent SDK: each role is a sandboxed Claude Code session in the step's clone."""

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import SandboxSettings

from shelf.ports.agents import AgentTask


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


WORKER_SECRETS = frozenset({"SESSION_SECRET", "GITHUB_WEBHOOK_SECRET"})
"""Settings of the worker that an agent has no use for. Whatever else starts with ``GITHUB_APP_`` is blanked too."""


def hidden_from_agents(environ: Mapping[str, str]) -> dict[str, str]:
    """The worker's secrets, blanked: an agent inherits the worker's environment, and none of this is for it.

    The model credential and ordinary variables (``PATH``, ``HOME``) are left alone, because the agent needs them.
    """
    return {name: "" for name in environ if name in WORKER_SECRETS or name.startswith("GITHUB_APP_")}


def options_for(
    task: AgentTask,
    *,
    nested_sandbox: bool = False,
    sandbox: bool = True,
    cli_path: str | None = None,
    allowed_domains: tuple[str, ...] = (),
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
        env={**hidden_from_agents(os.environ), **task.env},
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

    def _options(self, task: AgentTask) -> ClaudeAgentOptions:
        return options_for(
            task,
            nested_sandbox=self.nested_sandbox,
            sandbox=self.sandbox,
            cli_path=self.cli_path,
            allowed_domains=self.allowed_domains,
        )

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the final answer."""
        answer = ""
        async for message in query(
            prompt=task.prompt,
            options=self._options(task),
        ):
            if isinstance(message, ResultMessage):
                if message.is_error:
                    raise AgentFailedError(task.role.name, message.result or message.subtype)
                answer = message.result or ""
        return answer
