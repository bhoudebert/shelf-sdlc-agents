"""``AgentBackend`` over the Claude Agent SDK: each role is a sandboxed Claude Code session in the step's clone."""

from dataclasses import dataclass

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import SandboxSettings

from shelf.ports.agents import AgentTask


class AgentFailedError(RuntimeError):
    """The agent run ended in error."""

    def __init__(self, role: str, reason: str) -> None:
        """Say which role failed and why."""
        super().__init__(f"{role} failed: {reason}")


def options_for(task: AgentTask, *, nested_sandbox: bool = False) -> ClaudeAgentOptions:
    """The SDK options for ``task``: its own tools only, the sandbox on, bounded in turns and money.

    ``nested_sandbox`` selects the weaker sandbox mode that works inside a container (Docker).
    """
    return ClaudeAgentOptions(
        cwd=task.workdir,
        system_prompt=task.system_prompt,
        allowed_tools=list(task.role.tools),
        permission_mode="acceptEdits",
        max_turns=task.max_turns,
        max_budget_usd=task.max_budget_usd,
        model=task.model,
        env=dict(task.env),
        setting_sources=[],
        sandbox=SandboxSettings(enabled=True, autoAllowBashIfSandboxed=True, enableWeakerNestedSandbox=nested_sandbox),
    )


@dataclass(frozen=True, slots=True)
class ClaudeBackend:
    """Runs roles on the Claude Agent SDK. Credentials come from the environment of the worker."""

    nested_sandbox: bool = False

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the final answer."""
        answer = ""
        async for message in query(prompt=task.prompt, options=options_for(task, nested_sandbox=self.nested_sandbox)):
            if isinstance(message, ResultMessage):
                if message.is_error:
                    raise AgentFailedError(task.role.name, message.result or message.subtype)
                answer = message.result or ""
        return answer
