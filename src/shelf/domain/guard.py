"""What the guard (Warden) has seen of the agents' work, as the administrator reads it. Pure."""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GuardReport:
    """The counts of the guard's audit log."""

    calls: int
    """How many agent calls were recorded."""
    stopped: int
    """How many the guard stopped, or would have stopped had it not been only watching."""
    redactions: int
    """How many secrets or personal values it replaced by tokens."""
    chain_intact: bool
    """Whether no record of the log was changed or removed."""
    categories: Mapping[str, int] = field(default_factory=dict[str, int])
    """How often each kind of risk was found."""

    def top_categories(self, limit: int = 5) -> tuple[tuple[str, int], ...]:
        """The risks found most often, the most frequent first."""
        ranked = sorted(self.categories.items(), key=lambda item: (-item[1], item[0]))
        return tuple(ranked[:limit])
