"""What the agents used: tokens, cost, time and rounds, per step, per agent and for a whole work. Pure."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Usage:
    """What one step, or a sum of steps, used."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    """What the provider said it cost; ``None`` when it said nothing, which is not the same as free."""
    turns: int = 0
    seconds: float = 0.0
    models: tuple[str, ...] = ()

    @property
    def tokens(self) -> int:
        """Every token the provider counted, the cached ones included."""
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens

    def __add__(self, other: "Usage") -> "Usage":
        """The sum of two uses; a cost is the sum of the ones that were reported, none when neither was."""
        costs = [c for c in (self.cost_usd, other.cost_usd) if c is not None]
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
            sum(costs) if costs else None,
            self.turns + other.turns,
            self.seconds + other.seconds,
            tuple(dict.fromkeys((*self.models, *other.models))),
        )


@dataclass(frozen=True, slots=True)
class StepUsage:
    """What one agent step used, and which step it was."""

    phase: str
    attempt: int
    """The round: 0 for the first time the step ran, 1 for the first time it was sent back."""
    agent: str
    usage: Usage


@dataclass(frozen=True, slots=True)
class AgentTotal:
    """What one agent used over the whole work."""

    agent: str
    runs: int
    """How many times it ran."""
    usage: Usage


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """The steps of a work, each agent's total and the total of the work."""

    steps: tuple[StepUsage, ...]
    agents: tuple[AgentTotal, ...]
    total: Usage


def summarize(steps: Sequence[StepUsage]) -> UsageSummary:
    """Sum ``steps`` per agent, in the order each agent first ran, and for the whole work."""
    order: list[str] = []
    sums: dict[str, tuple[int, Usage]] = {}
    total = Usage()
    for step in steps:
        if step.agent not in sums:
            order.append(step.agent)
        runs, used = sums.get(step.agent, (0, Usage()))
        sums[step.agent] = (runs + 1, used + step.usage)
        total += step.usage
    return UsageSummary(tuple(steps), tuple(AgentTotal(name, *sums[name]) for name in order), total)
