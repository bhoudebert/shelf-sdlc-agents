"""What was settled without the person: the arbitrations, the points passed on, the assumptions (ADR 0021).

The merge is the one stop that always remains, so this is what its reader is shown first: everything the work decided
while nobody was asked, and which of it deserves a second look.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from shelf.domain.story import Message

LIMIT = 20
"""How many lines of each kind are shown."""
WHY_CHARS = 300

_ENTRY = re.compile(
    r"^## (?P<at>\S+) · arbitrator settled the disagreement at (?P<step>.+): (?P<verdict>fix|overrule|escalate)\s*$"
)
_PASSED = "nobody was there to decide, so the work went on"
_READ_THEM = "please read them before you merge."
_REVIEW = re.compile(r"I could not settle the (?P<step>.+?) with the writer")
_HEADING = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")
_DOCUMENTS = ("spec.md", "design.md", "plan.md")


@dataclass(frozen=True, slots=True)
class Line:
    """One thing that was settled without the person."""

    kind: str
    """``fixed`` or ``overruled`` (an arbitration), ``passed`` (a disagreement the work went on past), ``assumed``."""
    where: str
    """The step, or the document an assumption is in."""
    why: str
    """One line: what was decided and on what ground."""
    check: bool = False
    """Whether it deserves a look before the merge."""


@dataclass(frozen=True, slots=True)
class Settled:
    """Everything settled without the person, in the order a reader should look at it."""

    lines: tuple[Line, ...] = ()

    @property
    def to_check(self) -> tuple[Line, ...]:
        """The lines that ask for a look before the merge."""
        return tuple(line for line in self.lines if line.check)

    def __bool__(self) -> bool:
        """Whether anything was settled without the person."""
        return bool(self.lines)


def _short(text: str) -> str:
    one = " ".join(text.split())
    return one if len(one) <= WHY_CHARS else f"{one[:WHY_CHARS].rstrip()}…"


def _arbitrations(log: str) -> list[Line]:
    found: list[Line] = []
    entry: re.Match[str] | None = None
    quoted: list[str] = []

    def close() -> None:
        if entry is not None and entry["verdict"] != "escalate":  # an escalation was settled by a person
            overruled = entry["verdict"] == "overrule"
            found.append(
                Line(
                    "overruled" if overruled else "fixed",
                    entry["step"],
                    _short(" ".join(quoted)) or "(no reason given)",
                    check=overruled,
                )
            )

    for raw in log.splitlines():
        if matched := _ENTRY.match(raw):
            close()
            entry, quoted = matched, []
        elif entry is not None and raw.startswith(">"):
            quoted.append(raw.lstrip("> ").strip())
        elif raw.startswith("## "):
            close()
            entry, quoted = None, []
    close()
    return found


def _passed(messages: Sequence[Message]) -> list[Line]:
    found: list[Line] = []
    for message in messages:
        if _PASSED not in message.body:
            continue
        step = _REVIEW.search(message.body)
        points = message.body.split(_READ_THEM, 1)[-1].strip()
        found.append(Line("passed", step["step"] if step else "a review", _short(points), check=True))
    return found


def _assumptions(documents: Mapping[str, str]) -> list[Line]:
    found: list[Line] = []
    for name in (*_DOCUMENTS, *sorted(set(documents) - set(_DOCUMENTS))):
        inside = False
        for raw in documents.get(name, "").splitlines():
            heading = _HEADING.match(raw)
            if heading:
                inside = heading["title"].strip().lower() == "assumptions"
            elif inside and raw.strip():
                found.append(Line("assumed", name, _short(raw.strip().lstrip("-*0123456789. ").strip())))
    return found


def settled_of(documents: Mapping[str, str], messages: Sequence[Message]) -> Settled:
    """The lines to show, those to check first: overrules and passed disagreements, then fixes, then assumptions."""
    lines = [
        *_arbitrations(documents.get("decisions.md", "")),
        *_passed(messages),
        *_assumptions({name: text for name, text in documents.items() if name != "decisions.md"}),
    ]
    order = {"overruled": 0, "passed": 1, "fixed": 2, "assumed": 3}
    return Settled(tuple(sorted(lines, key=lambda line: order[line.kind])))


_PHRASE = {
    "overruled": "The arbitrator **overruled** the reviewer at the {where}",
    "passed": "The {where} could not be settled and the work **went on**",
    "fixed": "The arbitrator found the reviewer right at the {where} and the author **fixed** it",
    "assumed": "An agent **assumed** (in `{where}`)",
}


def markdown_of(settled: Settled) -> str:
    """The section for the comment on the pull request, ready to post."""
    if not settled:
        return (
            "**Settled without you:** nothing. No arbitrator was needed, nothing was passed on "
            "and no assumption was written."
        )
    lines = ["**Settled without you**", ""]
    if settled.to_check:
        lines += [f"{len(settled.to_check)} to check before you merge, marked ⚠️.", ""]
    for kind in ("overruled", "passed", "fixed", "assumed"):
        for line in [line for line in settled.lines if line.kind == kind][:LIMIT]:
            mark = "⚠️ " if line.check else ""
            lines.append(f"- {mark}{_PHRASE[kind].format(where=line.where)}: {line.why}")
    return "\n".join(lines)
