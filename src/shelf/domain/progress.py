"""The progress comment: one living summary on the pull request of what each step did, updated after every step."""

from collections.abc import Sequence
from dataclasses import dataclass

from shelf.domain.pipeline import Phase
from shelf.domain.stage import RUNNING_NAMES
from shelf.domain.work import Outcome, Produced, Reason, Reviewed, StepResult, Verdict, Verified

MARK = "<!-- shelf-progress:"
TITLE = "### shelf-sdlc: progress"


@dataclass(frozen=True, slots=True)
class Entry:
    """One thing that happened at a phase, in a few words."""

    phase: Phase
    text: str


@dataclass(frozen=True, slots=True)
class Position:
    """Where the work is now: at a phase, running or waiting for a person, or over with an outcome."""

    phase: Phase
    waiting: Reason | None = None
    outcome: Outcome | None = None


def marker(work_id: str) -> str:
    """The hidden line that lets the system find its own progress comment again."""
    return f"{MARK}{work_id} -->"


_VERDICT_WORDS: dict[Verdict, str] = {
    Verdict.APPROVE: "approved",
    Verdict.CHANGES: "asked for changes",
    Verdict.ESCALATE: "could not decide, needs a person",
}


def describe(result: StepResult, attempt: int) -> str:
    """What a finished step did, in a few words, with its round when it is not the first."""
    suffix = f" (round {attempt})" if attempt else ""
    match result:
        case Produced():
            return f"written{suffix}"
        case Reviewed(verdict):
            return f"{_VERDICT_WORDS[verdict]}{suffix}"
        case Verified(waiting=True):
            return f"waiting for CI{suffix}"
        case Verified(passed):
            return f"{'passed' if passed else 'failed'}{suffix}"


def _symbol(text: str) -> str:
    if text.startswith(("approved", "passed", "written", "you: approve")):
        return "✅"
    if text.startswith(("asked for changes", "failed", "you: changes")):
        return "🔁"
    if text.startswith("waiting for CI"):
        return "⏳"
    return "⚠️"


def _now(phase: Phase, waiting: Reason | None) -> str:
    if waiting is Reason.MERGE:
        return "✅ ready to review and merge"
    if waiting is not None:
        return f"⏸ waiting for you: {RUNNING_NAMES[phase]}"
    return f"⏳ {RUNNING_NAMES[phase]}"


def render_progress(
    work_id: str,
    phases: Sequence[Phase],
    log: Sequence[Entry],
    position: Position,
) -> str:
    """The markdown of the progress comment: a row per step of the course, what happened, and where the work is."""
    rows: list[str] = []
    for step in phases:
        events = [f"{_symbol(e.text)} {e.text}" for e in log if e.phase is step]
        if position.outcome is None and step is position.phase:
            events.append(_now(step, position.waiting))
        rows.append(f"| {RUNNING_NAMES[step].capitalize()} | {' → '.join(events) if events else '·'} |")
    state = {
        None: _now(position.phase, position.waiting),
        Outcome.MERGED: "✅ merged",
        Outcome.CLOSED: "closed without a merge",
        Outcome.ABORTED: "aborted",
    }[position.outcome]
    table = "\n".join(["| Step | What happened |", "| --- | --- |", *rows])
    return f"{marker(work_id)}\n{TITLE}\n\n{table}\n\n**Now:** {state}"
