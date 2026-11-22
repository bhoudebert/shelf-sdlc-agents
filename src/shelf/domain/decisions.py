"""The record of who decided what, and when: one entry for each decision a person makes, kept in the repository."""

from dataclasses import dataclass

from shelf.domain.config import GATE_ROLES, RepoConfig, Role
from shelf.domain.pipeline import Phase
from shelf.domain.work import ArbitrationVerdict, DecisionKind

FILE = "decisions.md"
"""The name of the log, in the work's documents folder."""

HEADER = (
    "# Decisions\n\n"
    "Who decided what, and when, on this work. The system appends an entry each time a person decides, and "
    "each time an arbitrator settles a disagreement; an agent never writes here itself.\n"
)

_SUBJECT: dict[Phase, str] = {
    Phase.SPEC_REVIEW: "the spec review",
    Phase.SPEC_APPROVAL: "the spec",
    Phase.DESIGN_REVIEW: "the design",
    Phase.CODE_REVIEW: "the code review",
    Phase.VERIFY: "the checks",
    Phase.PULL_REQUEST: "the pull request",
}
"""What a person's decision at a step is about, for the sentence of the entry."""


def _what(kind: DecisionKind, phase: Phase) -> str:
    step = phase.value.replace("_", " ")
    subject = _SUBJECT.get(phase, f"the {step}")
    match kind:
        case DecisionKind.APPROVE:
            return f"approved {subject}"
        case DecisionKind.CHANGES:
            return f"asked for changes to {subject}"
        case DecisionKind.RESUME:
            return f"resumed the work at {step}"
        case DecisionKind.REJECT:
            return f"rejected the work at {step}"
        case DecisionKind.ABORT:
            return f"aborted the work at {step}"


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """One decision of one person."""

    at: str
    """When, ISO, UTC."""
    login: str
    kind: DecisionKind
    phase: Phase
    """The step the work was waiting at."""
    note: str = ""
    acting: str = ""
    """How the person came to decide: the role they held, ``administrator``, or empty when nothing restricts them."""


def acted_as(config: RepoConfig, login: str, phase: Phase, *, admin: bool) -> str:
    """How ``login`` is entitled to decide at ``phase``: a role they hold for that gate, a role at all, or none.

    Nothing here ever refuses a person: it only says what the repository's roles make of them, for the record.
    """
    held = sorted(role for role, people in config.roles.items() if login in people)
    gate = GATE_ROLES.get(phase, frozenset[Role]())
    for_gate = [role.value for role in held if role in gate]
    if for_gate:
        return ", ".join(for_gate)
    if admin:
        return "administrator"
    if held:
        return f"{', '.join(role.value for role in held)} (not a role of this step)"
    return "no role" if config.roles else ""


def render_entry(record: DecisionRecord) -> str:
    """The entry for ``record``, ready to append."""
    lines = [f"## {record.at} · {record.login} {_what(record.kind, record.phase)}", ""]
    details: list[str] = []
    if record.acting:
        details += [f"- Acting as: {record.acting}"]
    if record.note.strip():
        details += ["- Note:", *(f"  > {line}" if line else "  >" for line in record.note.strip().splitlines())]
    lines += [*details, ""] if details else []
    return "\n".join(lines) + "\n"


def append_entry(existing: str, record: DecisionRecord) -> str:
    """``existing`` with the entry added at the end; the log is created with its header when there is none."""
    base = existing if existing.strip() else HEADER
    return base.rstrip("\n") + "\n\n" + render_entry(record).rstrip("\n") + "\n"


def render_arbitration(at: str, phase: Phase, verdict: ArbitrationVerdict, text: str) -> str:
    """The entry for an arbitration, ready to append: what it decided, and what it said."""
    step = phase.value.replace("_", " ")
    lines = [f"## {at} · arbitrator settled the disagreement at {step}: {verdict.value}", ""]
    if text.strip():
        lines += [*(f"> {line}" if line else ">" for line in text.strip().splitlines()), ""]
    return "\n".join(lines) + "\n"


def append_arbitration(existing: str, at: str, phase: Phase, verdict: ArbitrationVerdict, text: str) -> str:
    """``existing`` with the arbitration added at the end; the log is created with its header when there is none."""
    base = existing if existing.strip() else HEADER
    return base.rstrip("\n") + "\n\n" + render_arbitration(at, phase, verdict, text).rstrip("\n") + "\n"
