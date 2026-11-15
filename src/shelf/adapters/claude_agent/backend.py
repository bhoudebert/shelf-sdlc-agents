"""``AgentBackend`` over the Claude Agent SDK: each role is a sandboxed Claude Code session in the step's clone."""

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import SandboxSettings

from shelf.domain.secrets import hidden_from_agents
from shelf.domain.usage import Usage
from shelf.ports.agents import AgentTask

log = logging.getLogger(__name__)

AGENT_ENVIRONMENT = {"DO_NOT_TRACK": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
"""Telemetry off, and no memory carried from one step to the next: an agent starts each step from the repository."""


def usage_of(message: ResultMessage) -> Usage:
    """What the run used, as the provider reported it: a figure not reported is zero, a cost not reported is none."""
    used: dict[str, Any] = dict(message.usage or {})
    return Usage(
        input_tokens=int(used.get("input_tokens") or 0),
        output_tokens=int(used.get("output_tokens") or 0),
        cache_read_tokens=int(used.get("cache_read_input_tokens") or 0),
        cache_write_tokens=int(used.get("cache_creation_input_tokens") or 0),
        cost_usd=message.total_cost_usd,
        turns=int(message.num_turns or 0),
        seconds=round((message.duration_ms or 0) / 1000, 1),
        models=tuple(sorted(message.model_usage or {})),
    )


def step_summary(role: str, message: ResultMessage) -> str:
    """One line about a finished step: turns, time, cost. Never the prompt, the answer or a secret."""
    cost = f"${message.total_cost_usd:.4f}" if message.total_cost_usd is not None else "unknown"
    refused = len(message.permission_denials or [])
    return (
        f"agent step finished: role={role} turns={message.num_turns} seconds={round(message.duration_ms / 1000)} "
        f"cost={cost}" + (f" refused_tool_calls={refused}" if refused else "")
    )


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


WEB_TOOLS = ("WebFetch", "WebSearch")
"""Reading the web. Not part of a role: the operator can turn them off for every agent."""


def options_for(  # noqa: PLR0913 - one argument per setting the operator controls
    task: AgentTask,
    *,
    nested_sandbox: bool = False,
    sandbox: bool = True,
    cli_path: str | None = None,
    allowed_domains: tuple[str, ...] = (),
    bundles: tuple[Path, ...] = (),
    web: bool = False,
) -> ClaudeAgentOptions:
    """The SDK options for ``task``: its own tools only, the sandbox on, bounded in turns and money.

    ``web`` adds the tools that read the web: Warden judges each call, and what they fetch is text, never a download.
    ``nested_sandbox`` selects the weaker sandbox mode that works inside a container (Docker). ``sandbox=False`` turns
    the sandbox off, for hosts where it cannot start: the container is then the only boundary around the agent.
    """
    return ClaudeAgentOptions(
        cwd=task.workdir,
        system_prompt={"type": "preset", "preset": "claude_code", "append": task.system_prompt},
        allowed_tools=[*task.role.tools, *(WEB_TOOLS if web else ())],
        resume=task.resume or None,
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
    web: bool = False
    """Whether agents may read the web (``SHELF_WEB``)."""
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
            web=self.web,
        )

    async def run(self, task: AgentTask) -> str:
        """Run ``task`` and return the final answer; a session that cannot be continued starts again from scratch."""
        if task.resume:
            try:
                return await self._run_once(task)
            except Exception as error:  # noqa: BLE001 - whatever stopped the continuation, the step must still run
                log.warning("could not continue the session of %s (%s): starting again", task.role.name, error)
                task = replace(task, resume="", prompt=task.fallback_prompt or task.prompt)
        return await self._run_once(task)

    async def _run_once(self, task: AgentTask) -> str:
        answer = ""
        async for message in query(
            prompt=task.prompt,
            options=self.options(task),
        ):
            if isinstance(message, ResultMessage):
                log.info(step_summary(task.role.name, message))
                if task.sink is not None:
                    task.sink.usage = usage_of(message)
                    task.sink.session_id = message.session_id or ""
                if message.is_error:
                    raise AgentFailedError(task.role.name, message.result or message.subtype)
                answer = message.result or ""
        return answer
