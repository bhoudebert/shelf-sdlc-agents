"""What the guard (Warden) has seen of the agents' work, as the administrator reads it. Pure."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

ALWAYS_REFUSED = frozenset({"blocked_domain", "tamper"})
"""The risks no rule can allow: the guard refuses them whatever a policy says."""


@dataclass(frozen=True, slots=True)
class StoppedCall:
    """One call the guard stopped, or would have stopped had it not been only watching."""

    at: str
    agent: str
    session: str
    kind: str
    decision: str
    intended: str
    categories: tuple[str, ...]
    reason: str
    summary: str
    """The command or address, redacted and shortened by the guard."""

    @property
    def can_be_allowed(self) -> bool:
        """Whether a rule of the operator's policy could allow this call."""
        return not ALWAYS_REFUSED.intersection(self.categories)

    def rule_to_allow(self) -> str | None:
        """A rule for the operator's policy file that allows exactly this command, or ``None`` when none can.

        Only a command is matched, and exactly: a rule that allows more than what was seen is the administrator's to
        write. The text is for a person to read and copy; nothing here applies it.
        """
        if not self.can_be_allowed or self.kind != "bash" or not self.summary:
            return None
        return (
            "[[rules]]\n"
            f'id = "allow-{re.sub(r"[^a-z0-9]+", "-", self.summary.lower()).strip("-")[:40] or "command"}"\n'
            f"match = '^{_regex_of(self.summary)}$'\n"
            'decision = "allow"\n'
            'reason = "approved by the administrator"\n'
        )


_META = frozenset("\\.+*?()|[]{}^$")


def _regex_of(text: str) -> str:
    """``text`` as a regular expression that matches exactly it, written to sit inside a TOML literal string.

    A literal string cannot hold a quote, so a quote matches any one character instead.
    """
    return "".join("." if char == "'" else f"\\{char}" if char in _META else char for char in text)


def rule_to_deny_host(host: str) -> str:
    """The line of the operator's policy file that denies a host, for a person to copy."""
    return f'[network]\ndeny_domains = ["{host}"]\n'


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
    recent: tuple[StoppedCall, ...] = ()
    """The latest calls the guard stopped or would have stopped, newest first."""
    web_hosts: Mapping[str, int] = field(default_factory=dict[str, int])
    """Each host the agents fetched, with how many times."""

    def top_categories(self, limit: int = 5) -> tuple[tuple[str, int], ...]:
        """The risks found most often, the most frequent first."""
        ranked = sorted(self.categories.items(), key=lambda item: (-item[1], item[0]))
        return tuple(ranked[:limit])
