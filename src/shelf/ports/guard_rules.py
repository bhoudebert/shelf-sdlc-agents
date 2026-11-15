"""Where the rules an administrator adds to the guard are kept."""

from typing import Protocol

from shelf.domain.guard_rules import OverlayRule


class GuardRules(Protocol):
    """The overlay the guard reads: rules added from the admin page, each with who and when."""

    async def rules(self) -> tuple[OverlayRule, ...]:
        """The rules in force, oldest first."""
        ...

    async def add(self, rule: OverlayRule) -> None:
        """Keep ``rule`` and make the guard read it from its next call. Adding the same rule twice changes nothing."""
        ...

    async def remove(self, rule_id: str, by: str, at: str) -> bool:
        """Take a rule out. ``False`` when there is no such rule."""
        ...
