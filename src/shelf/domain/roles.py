"""The agent roles: which phase each one serves, what it may touch, and what it must leave behind."""

from dataclasses import dataclass
from typing import Final

from shelf.domain.model import WorkId
from shelf.domain.pipeline import KIND, EntryPoint, Kind, Phase

READ_ONLY: Final = ("Read", "Glob", "Grep")
WRITING: Final = (*READ_ONLY, "Write", "Edit")
CODING: Final = (*WRITING, "Bash")


@dataclass(frozen=True, slots=True)
class AgentRole:
    """One role: its name (also the name of its prompt), its tools and the document it produces, if any."""

    name: str
    tools: tuple[str, ...]
    document: str = ""
    """File name under the work's document folder, for roles that write one."""


ROLES: dict[Phase, AgentRole] = {
    Phase.INTAKE: AgentRole("intake", WRITING, "spec.md"),
    Phase.SPEC_REVIEW: AgentRole("spec_critic", READ_ONLY),
    Phase.DESIGN: AgentRole("architect", WRITING, "design.md"),
    Phase.DESIGN_REVIEW: AgentRole("design_reviewer", READ_ONLY),
    Phase.PLAN: AgentRole("planner", WRITING, "plan.md"),
    Phase.IMPLEMENT: AgentRole("implementer", CODING),
    Phase.CODE_REVIEW: AgentRole("code_reviewer", READ_ONLY),
}
"""Phases that an agent carries out. The checks, the gate and the pull request have no agent."""

REVIEWERS: frozenset[Phase] = frozenset(phase for phase in ROLES if KIND[phase] is Kind.REVIEW)


def documents_dir(work_id: WorkId) -> str:
    """Where the work keeps its spec, design and plan inside the repository."""
    return f"docs/shelf/{work_id}"


PROVIDED_DOCUMENT: dict[EntryPoint, str] = {
    EntryPoint.NEED: "request.md",
    EntryPoint.SPEC: "spec.md",
    EntryPoint.DESIGN: "spec.md",
    EntryPoint.PLAN: "design.md",
    EntryPoint.IMPLEMENT: "plan.md",
}
"""The file the text a person submits is recorded as, so every agent and reviewer reads it from the repository."""
