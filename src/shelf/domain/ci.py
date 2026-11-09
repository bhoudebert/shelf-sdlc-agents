"""What the repository's own continuous integration says about a branch, read as one answer."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum, auto

PASSING = frozenset({"success", "neutral", "skipped"})
"""Conclusions that let the work go on."""

NEEDS_A_PERSON = frozenset({"action_required"})
"""Conclusions that wait for a person on GitHub (a workflow from a fork that nobody approved, for instance)."""


def is_red(conclusion: str) -> bool:
    """Whether a finished run counts against the commit: anything that is not a pass.

    That includes ``cancelled``, ``timed_out`` and ``startup_failure`` (a run that did not finish proved nothing)
    and any conclusion GitHub adds later, which is safer to stop on than to ignore.
    """
    return conclusion not in PASSING and conclusion not in NEEDS_A_PERSON


LIMIT = 8
"""How many failing runs are named in a report."""


class CiState(StrEnum):
    """The one word that sums up all the runs of a commit."""

    NONE = auto()
    """No run exists for the commit: the repository has no CI, or it has not started."""
    PENDING = auto()
    """At least one run has not finished."""
    GREEN = auto()
    """Every run finished and none failed."""
    RED = auto()
    """At least one run failed, timed out or was cancelled."""
    BLOCKED = auto()
    """Nothing failed, but a run waits for a person to approve it."""


@dataclass(frozen=True, slots=True)
class CiRun:
    """One check run or commit status."""

    name: str
    status: str
    """``queued``, ``in_progress`` or ``completed``; a commit status is ``completed`` once it is not ``pending``."""
    conclusion: str = ""
    link: str = ""
    detail: str = ""
    """What the run says about itself: its summary and annotations, to tell the implementer what to fix."""


@dataclass(frozen=True, slots=True)
class Ci:
    """All the runs of a commit and their sum."""

    state: CiState
    runs: tuple[CiRun, ...] = ()

    @property
    def settled(self) -> bool:
        """Whether nothing is left to wait for."""
        return self.state is not CiState.PENDING

    @property
    def failing(self) -> tuple[CiRun, ...]:
        """The runs that are red."""
        return tuple(run for run in self.runs if run.status == "completed" and is_red(run.conclusion))

    def report(self) -> str:
        """What a person or an agent reads: the state, and for each red run its name, link and what it says."""
        lines = [f"CI is {self.state.value}."]
        for run in self.failing[:LIMIT]:
            link = f" ({run.link})" if run.link else ""
            lines.append(f"- {run.name}: {run.conclusion}{link}")
            if run.detail:
                lines.append(_indent(run.detail))
        waiting = [run.name for run in self.runs if run.status != "completed"]
        if waiting:
            lines.append("Still running: " + ", ".join(waiting[:LIMIT]))
        asked = [run.name for run in self.runs if run.conclusion in NEEDS_A_PERSON]
        if asked:
            lines.append("Waiting for someone to approve it on GitHub: " + ", ".join(asked[:LIMIT]))
        return "\n".join(lines)


def judge(runs: Sequence[CiRun]) -> Ci:
    """Sum up ``runs``. Red wins over pending, because there is no reason to wait for a commit that already failed."""
    found = tuple(runs)
    if not found:
        return Ci(CiState.NONE)
    if any(run.status == "completed" and is_red(run.conclusion) for run in found):
        return Ci(CiState.RED, found)
    if any(run.status != "completed" for run in found):
        return Ci(CiState.PENDING, found)
    if any(run.conclusion in NEEDS_A_PERSON for run in found):
        return Ci(CiState.BLOCKED, found)
    return Ci(CiState.GREEN, found)


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" for line in text.strip().splitlines())
