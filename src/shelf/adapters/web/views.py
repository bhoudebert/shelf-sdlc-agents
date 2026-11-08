"""What the templates show: plain view models built from domain values, with the words people read."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from markdown_it import MarkdownIt
from markupsafe import Markup

from shelf.adapters.web.webhook_log import Delivery, Result
from shelf.domain.model import WorkView
from shelf.domain.pipeline import PIPELINE, EntryPoint, Phase
from shelf.domain.roles import DOCUMENT_TITLES
from shelf.domain.work import DecisionKind, Outcome, Reason

ENTRY_LABELS: dict[EntryPoint, tuple[str, str]] = {
    EntryPoint.NEED: ("A need", "Describe what you want. The factory writes the spec first."),
    EntryPoint.SPEC: ("A spec", "You wrote the spec. It is reviewed, then you approve it."),
    EntryPoint.DESIGN: ("A design to make", "The spec is approved. Start at the design."),
    EntryPoint.PLAN: ("A plan to make", "The design is done. Start at the plan."),
    EntryPoint.IMPLEMENT: ("Code to write", "The plan is done. Start implementing."),
    EntryPoint.PULL_REQUEST_REVIEW: ("Review my pull request", "A pull request already exists. Get it reviewed."),
}

PHASE_LABELS: dict[Phase, str] = {
    Phase.INTAKE: "Spec",
    Phase.SPEC_REVIEW: "Spec review",
    Phase.SPEC_APPROVAL: "Spec approval",
    Phase.DESIGN: "Design",
    Phase.DESIGN_REVIEW: "Design review",
    Phase.PLAN: "Plan",
    Phase.IMPLEMENT: "Implementation",
    Phase.VERIFY: "Checks",
    Phase.CODE_REVIEW: "Code review",
    Phase.PULL_REQUEST: "Pull request",
}

WAIT_LABELS: dict[Reason, str] = {
    Reason.GATE: "Waiting for your approval",
    Reason.ESCALATION: "A person is needed",
    Reason.FAILURE: "A step failed",
    Reason.MERGE: "Waiting for the merge",
}

OUTCOME_LABELS: dict[Outcome, str] = {
    Outcome.MERGED: "Merged",
    Outcome.CLOSED: "Closed",
    Outcome.ABORTED: "Aborted",
}

DECISION_LABELS: dict[DecisionKind, tuple[str, bool]] = {
    DecisionKind.APPROVE: ("Approve", False),
    DecisionKind.CHANGES: ("Request changes", True),
    DecisionKind.RESUME: ("Resume", False),
    DecisionKind.REJECT: ("Reject", False),
    DecisionKind.ABORT: ("Abort", False),
}


class Status(StrEnum):
    """The three states a card can be in."""

    RUNNING = "running"
    WAITING = "waiting"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class EntryOption:
    """One way to start, for the start form."""

    value: str
    label: str
    help: str
    needs_pull_request: bool


@dataclass(frozen=True, slots=True)
class DecisionOption:
    """One button on a piece of work waiting for a person."""

    value: str
    label: str
    needs_note: bool


@dataclass(frozen=True, slots=True)
class TimelineStep:
    """One compartment of the pipeline, as it stands for this work."""

    label: str
    state: str
    """``done``, ``current``, ``waiting``, ``stopped`` or ``todo``."""


@dataclass(frozen=True, slots=True)
class ItemView:
    """A piece of work as the board and its page show it."""

    id: str
    repo: str
    requester: str
    entry: str
    phase: str
    status: Status
    waiting: str
    detail: str
    outcome: str
    pull_request_url: str
    reason: str


def entry_options(allowed: frozenset[EntryPoint]) -> list[EntryOption]:
    """The entry points a repository enables, in pipeline order."""
    return [
        EntryOption(
            entry.value, ENTRY_LABELS[entry][0], ENTRY_LABELS[entry][1], entry is EntryPoint.PULL_REQUEST_REVIEW
        )
        for entry in EntryPoint
        if entry in allowed
    ]


_DECISIONS: dict[Reason, tuple[DecisionKind, ...]] = {
    Reason.GATE: (DecisionKind.APPROVE, DecisionKind.CHANGES, DecisionKind.REJECT, DecisionKind.ABORT),
    Reason.ESCALATION: (DecisionKind.APPROVE, DecisionKind.CHANGES, DecisionKind.REJECT, DecisionKind.ABORT),
    Reason.FAILURE: (DecisionKind.RESUME, DecisionKind.CHANGES, DecisionKind.REJECT, DecisionKind.ABORT),
    Reason.MERGE: (DecisionKind.CHANGES, DecisionKind.REJECT, DecisionKind.ABORT),
}


def decision_options(reason: Reason | None) -> list[DecisionOption]:
    """The buttons that make sense for what the work waits for."""
    if reason is None:
        return []
    return [DecisionOption(kind.value, *DECISION_LABELS[kind]) for kind in _DECISIONS[reason]]


def item_view(work: WorkView) -> ItemView:
    """Words for one piece of work."""
    if work.outcome is not None:
        status = Status.DONE
    elif work.waiting_for is not None:
        status = Status.WAITING
    else:
        status = Status.RUNNING
    return ItemView(
        id=work.id,
        repo=work.repo.full_name,
        requester=work.requester,
        entry=ENTRY_LABELS[work.entry][0],
        phase=PHASE_LABELS[work.phase],
        status=status,
        waiting=WAIT_LABELS[work.waiting_for] if work.waiting_for else "",
        detail=work.detail,
        outcome=OUTCOME_LABELS[work.outcome] if work.outcome else "",
        pull_request_url=work.pull_request_url,
        reason=work.waiting_for.value if work.waiting_for else "",
    )


def timeline(work: WorkView) -> list[TimelineStep]:
    """The pipeline with where this work stands: what is done, the current phase, and what is still ahead."""
    position = PIPELINE.index(work.phase)
    merged = work.outcome is Outcome.MERGED
    steps: list[TimelineStep] = []
    for index, phase in enumerate(PIPELINE):
        if merged or index < position:
            state = "done"
        elif index > position:
            state = "todo"
        elif work.outcome is not None:
            state = "stopped"
        else:
            state = "waiting" if work.waiting_for is not None else "current"
        steps.append(TimelineStep(PHASE_LABELS[phase], state))
    return steps


_MARKDOWN = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")


def render_markdown(text: str) -> Markup:
    """Markdown to HTML for display. Raw HTML in the text is shown as text and dangerous links are dropped.

    The documents are written by agents from untrusted repository content, so nothing in them may become markup.
    """
    return Markup(_MARKDOWN.render(text))  # noqa: S704 - markdown-it escapes raw HTML and refuses unsafe link schemes


@dataclass(frozen=True, slots=True)
class DocumentView:
    """One document of a piece of work, ready to show."""

    name: str
    title: str
    html: Markup
    open: bool


def document_views(documents: Mapping[str, str], current: Phase) -> list[DocumentView]:
    """The documents that exist, in reading order. The one the work is at is open, the others folded."""
    focus = FOCUS.get(current)
    return [
        DocumentView(name, DOCUMENT_TITLES[name], render_markdown(documents[name]), open=name == focus)
        for name in DOCUMENT_TITLES
        if name in documents
    ]


FOCUS: dict[Phase, str] = {
    Phase.INTAKE: "request.md",
    Phase.SPEC_REVIEW: "spec.md",
    Phase.SPEC_APPROVAL: "spec.md",
    Phase.DESIGN: "spec.md",
    Phase.DESIGN_REVIEW: "design.md",
    Phase.PLAN: "design.md",
    Phase.IMPLEMENT: "plan.md",
    Phase.VERIFY: "plan.md",
    Phase.CODE_REVIEW: "plan.md",
    Phase.PULL_REQUEST: "plan.md",
}
"""Which document is the one to read when the work is at a phase."""


def version_of(*parts: object) -> str:
    """A short fingerprint of what a refreshing section shows. Equal fingerprints mean there is nothing new to draw."""
    return hashlib.sha1(repr(parts).encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class WebhookStatus:
    """What the interface tells an administrator about the GitHub webhook."""

    level: str
    """``ok``, ``warning`` or ``error``."""
    text: str


def ago(then: datetime, now: datetime) -> str:
    """How long ago, in a few words."""
    seconds = int((now - then).total_seconds())
    if seconds < 60:  # noqa: PLR2004
        return "moments ago"
    if seconds < 3600:  # noqa: PLR2004
        return f"{seconds // 60} min ago"
    return f"{seconds // 3600} h ago"


def webhook_status(last: Delivery | None, now: datetime) -> WebhookStatus:
    """Say, for an administrator, whether GitHub's webhooks reach this instance and what became of the last one."""
    if last is None:
        return WebhookStatus(
            "warning",
            "No GitHub webhook has reached this instance since it started. A command typed on a pull request is then "
            "only noticed by the periodic check, every 5 to 60 minutes. On the App's settings page, Advanced, Recent "
            "deliveries, see whether GitHub sends them and what we answer: the webhook URL, the secret and the "
            "subscribed events (Pull request, Issue comment) must match.",
        )
    when = f"{last.event}, {ago(last.at, now)}"
    match last.result:
        case Result.BAD_SIGNATURE:
            return WebhookStatus(
                "error",
                f"The last webhook ({when}) was refused: its signature does not match GITHUB_WEBHOOK_SECRET. "
                "Use the same secret in the App's webhook settings and in deploy/.env, then redeliver it.",
            )
        case Result.REFUSED:
            return WebhookStatus("warning", f"The last command from GitHub ({when}) was not applied: {last.detail}")
        case Result.APPLIED:
            return WebhookStatus("ok", f"GitHub webhooks arrive. Last one: {when}, applied: {last.detail}.")
        case Result.IGNORED:
            return WebhookStatus("ok", f"GitHub webhooks arrive. Last one: {when}.")
