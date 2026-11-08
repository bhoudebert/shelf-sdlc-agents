"""The agent roles: which phase each one serves, what it may touch, and what it must leave behind."""

from dataclasses import dataclass
from typing import Final

from shelf.domain.model import WorkId
from shelf.domain.pipeline import KIND, EntryPoint, Kind, Phase

WORKING: Final = ("Read", "Glob", "Grep", "Write", "Edit", "Bash")
"""The normal Claude Code toolset. Agents work in a throwaway clone with no credentials: a reviewer may run git, tests
and linters like anyone, and what it changes is discarded because only producers' work is committed."""


@dataclass(frozen=True, slots=True)
class AgentRole:
    """One role: its name (also the name of its prompt), its tools and the document it produces, if any."""

    name: str
    tools: tuple[str, ...]
    document: str = ""
    """File name under the work's document folder, for roles that write one."""


TITLER = AgentRole("titler", WORKING)
"""Not a phase of the pipeline: names the pull request by the repository's own convention."""

ROLES: dict[Phase, AgentRole] = {
    Phase.INTAKE: AgentRole("intake", WORKING, "spec.md"),
    Phase.SPEC_REVIEW: AgentRole("spec_critic", WORKING),
    Phase.DESIGN: AgentRole("architect", WORKING, "design.md"),
    Phase.DESIGN_REVIEW: AgentRole("design_reviewer", WORKING),
    Phase.PLAN: AgentRole("planner", WORKING, "plan.md"),
    Phase.IMPLEMENT: AgentRole("implementer", WORKING),
    Phase.CODE_REVIEW: AgentRole("code_reviewer", WORKING),
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

DOCUMENT_TITLES: dict[str, str] = {
    "request.md": "The request",
    "spec.md": "Spec",
    "design.md": "Design",
    "plan.md": "Plan",
}
"""The documents of a piece of work, in the order a person reads them, with their titles."""
