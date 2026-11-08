"""Per-repository configuration and who may decide what."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum, auto

from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.policy import Policy


class Role(StrEnum):
    """What a person is for in a repository."""

    PRODUCT_OWNER = auto()
    ARCHITECT = auto()
    TECH_LEAD = auto()
    DEVELOPER = auto()


GATE_ROLES: dict[Phase, frozenset[Role]] = {
    Phase.SPEC_APPROVAL: frozenset({Role.PRODUCT_OWNER}),
    Phase.DESIGN_REVIEW: frozenset({Role.ARCHITECT, Role.TECH_LEAD}),
    Phase.PULL_REQUEST: frozenset({Role.TECH_LEAD, Role.DEVELOPER}),
}
"""Who may decide when work waits at a phase. A phase not listed is open to every listed member."""


@dataclass(frozen=True, slots=True)
class RepoConfig:
    """The ``.shelf/config.toml`` of a repository, with an administrator's overrides applied."""

    policy: Policy = field(default_factory=Policy)
    entries: frozenset[EntryPoint] = frozenset(EntryPoint)
    base_branch: str = "main"
    checks: tuple[str, ...] = ()
    roles: Mapping[Role, frozenset[str]] = field(default_factory=dict[Role, frozenset[str]])

    def members(self) -> frozenset[str]:
        """Everyone with a role."""
        return frozenset[str]().union(*self.roles.values())


def may_decide(config: RepoConfig, login: str, phase: Phase, *, admin: bool = False) -> bool:
    """Whether ``login`` may decide for work waiting at ``phase``.

    An administrator always may. With no role configured anyone signed in may: roles are an opt-in limit.
    """
    if admin or not config.roles:
        return True
    allowed = GATE_ROLES.get(phase)
    if allowed is None:
        return login in config.members()
    return any(login in config.roles.get(role, frozenset()) for role in allowed)
