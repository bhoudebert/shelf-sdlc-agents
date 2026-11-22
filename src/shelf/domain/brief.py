"""What a person who is asked to settle a disagreement reads first: the question, what is open, and a recommendation."""

import re
from dataclasses import dataclass

DISPUTE_MARK = "\n\n---\nThe dispute:\n"
"""Between an arbitrator's brief and the dispute it could not settle, in the detail of a wait."""

SHORT_LINES = 4
SHORT_CHARS = 500

_QUESTION = re.compile(r"^\s*Question:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RECOMMENDED = re.compile(r"^\s*Recommended answer:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_AGREE = re.compile(r"disagree, (\d+) point\(s\) came back", re.IGNORECASE)
_ROUNDS = re.compile(r"limit of (\d+) rounds reached", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Brief:
    """A wait at a disagreement, made readable."""

    question: str
    """One line: what is asked of the person."""
    short: str
    """The first lines of what is still open."""
    dispute: str
    """What could not be settled, in full."""
    arbitrated: bool = False
    """Whether an arbitrator looked at it and could not decide."""
    brief: str = ""
    """The arbitrator's own words, in full; empty when no one arbitrated."""
    recommended: str = ""
    """What to send to the agents if the person agrees with the arbitrator; empty when there is none."""


def _shortened(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()][:SHORT_LINES]
    shown = "\n".join(lines)
    return shown if len(shown) <= SHORT_CHARS else f"{shown[:SHORT_CHARS].rstrip()}…"


def _question_of(dispute: str) -> str:
    if found := _AGREE.search(dispute):
        return f"The reviewer and the author cannot agree: {found.group(1)} point(s) came back. What should happen?"
    if found := _ROUNDS.search(dispute):
        return f"The review used its {found.group(1)} rounds without agreeing. What should happen?"
    return "The reviewer could not decide. What should happen?"


def brief_of(detail: str) -> Brief:
    """Read the detail of a wait at a disagreement: an arbitrator's brief before the dispute, or the dispute alone."""
    head, mark, tail = detail.partition(DISPUTE_MARK)
    if not mark:
        return Brief(_question_of(detail), _shortened(detail), detail.strip())
    question = _QUESTION.search(head)
    recommended = _RECOMMENDED.search(head)
    first = next((line.strip() for line in head.splitlines() if line.strip()), "")
    return Brief(
        question.group(1) if question else first or _question_of(tail),
        _shortened(tail),
        tail.strip(),
        arbitrated=True,
        brief=head.strip(),
        recommended=recommended.group(1) if recommended else "",
    )
