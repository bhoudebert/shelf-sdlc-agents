"""``AgentBackend`` over the Claude Agent SDK: each role is a sandboxed Claude Code session in the step's clone."""

import json
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


def options_for(
    task: AgentTask, *, nested_sandbox: bool = False, sandbox: bool = True, cli_path: str | None = None
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
        env=dict(task.env),
        # The repository's own agent files (CLAUDE.md, skills, commands) are how it tells an agent its conventions.
        # Its hooks and MCP servers are code that would run in the worker: they are never loaded.
        setting_sources=["project"],
        settings=json.dumps({"disableAllHooks": True}),
        strict_mcp_config=True,
        sandbox=SandboxSettings(
            enabled=sandbox, autoAllowBashIfSandboxed=True, enableWeakerNestedSandbox=nested_sandbox
        ),
    )


@dataclass(frozen=True, slots=True)
class ClaudeBackend:
    """Runs roles on the Claude Agent SDK. Credentials come from the environment of the worker."""

    nested_sandbox: bool = False
    sandbox: bool = True
    cli_path: str | None = None
    """A specific Claude Code executable to use instead of the one bundled with the SDK."""

    def _options(self, task: AgentTask) -> ClaudeAgentOptions:
        return options_for(task, nested_sandbox=self.nested_sandbox, sandbox=self.sandbox, cli_path=self.cli_path)

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
