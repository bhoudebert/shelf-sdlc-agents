"""Running one step in a container of its own: what is asked of the runner, and the task inside the request."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

from shelf.domain.roles import AgentRole
from shelf.ports.agents import AgentTask


@dataclass(frozen=True, slots=True)
class StepRequest:
    """One step to run. The runner builds the container itself: no field here is a container option (decision 0019)."""

    key: str
    """Asking again with the same key returns the same step, never a second container."""
    kind: str = "agent"
    repo: str = ""
    """``owner/name``: selects the repository's tools volume."""
    session: str = ""
    """The work's sessions folder, so that a later step of the same work can continue the agent's session."""
    env: Mapping[str, str] = field(default_factory=dict[str, str])
    input: Mapping[str, Any] = field(default_factory=dict[str, Any])


class StepRunner(Protocol):
    """The runner service: starts the container for a request and streams back the lines the step wrote."""

    def run(self, request: StepRequest) -> AsyncIterator[str]:
        """The lines of the step, one JSON object each, the last one written by the runner."""
        ...


@dataclass(frozen=True, slots=True)
class StepSettings:
    """What the worker decides for a step beyond the task: the settings the sandbox path read from its own fields."""

    web: bool = False
    allowed_domains: tuple[str, ...] = ()
    bundles: tuple[str, ...] = ()
    """Names of the skill bundles bound to the role, looked up in the catalog baked into the image."""


def task_input(task: AgentTask, settings: StepSettings) -> dict[str, Any]:
    """The task as plain data for ``StepRequest.input``. The working copy and the environment travel apart."""
    return {
        "role": {"name": task.role.name, "tools": list(task.role.tools), "document": task.role.document},
        "system_prompt": task.system_prompt,
        "prompt": task.prompt,
        "max_turns": task.max_turns,
        "max_budget_usd": task.max_budget_usd,
        "model": task.model,
        "resume": task.resume,
        "fallback_prompt": task.fallback_prompt,
        "web": settings.web,
        "allowed_domains": list(settings.allowed_domains),
        "bundles": list(settings.bundles),
    }


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key, "")
    return value if isinstance(value, str) else ""


def _names(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key)
    return tuple(str(item) for item in cast("list[object]", value)) if isinstance(value, list) else ()


def task_from_input(data: Mapping[str, Any], workdir: Path) -> tuple[AgentTask, StepSettings]:
    """The task and settings a step container rebuilds from its input; the inverse of ``task_input``."""
    role = data.get("role")
    given = cast("dict[str, Any]", role) if isinstance(role, dict) else {}
    budget = data.get("max_budget_usd")
    turns = data.get("max_turns")
    task = AgentTask(
        role=AgentRole(_text(given, "name"), _names(given, "tools"), _text(given, "document")),
        system_prompt=_text(data, "system_prompt"),
        prompt=_text(data, "prompt"),
        workdir=workdir,
        max_turns=turns if isinstance(turns, int) and not isinstance(turns, bool) else 40,
        max_budget_usd=float(budget) if isinstance(budget, int | float) and not isinstance(budget, bool) else None,
        model=_text(data, "model") or None,
        resume=_text(data, "resume"),
        fallback_prompt=_text(data, "fallback_prompt"),
    )
    settings = StepSettings(
        web=data.get("web") is True,
        allowed_domains=_names(data, "allowed_domains"),
        bundles=_names(data, "bundles"),
    )
    return task, settings
