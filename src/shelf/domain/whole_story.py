"""The whole story of a work, as one text for the arbitrator: nothing of what led to a disagreement is left out."""

from collections.abc import Mapping, Sequence

from shelf.domain.roles import DOCUMENT_TITLES
from shelf.domain.runlog import RunRecord
from shelf.domain.story import Message

FILE = "story.md"
"""The name of the file the arbitrator reads, in the work's documents folder of its throwaway clone."""

DOCUMENT_ORDER = ("request.md", "spec.md", "design.md", "plan.md", "decisions.md")
LIMIT = 400_000
"""Characters of one part kept before it is cut with a mark that says so: a safeguard, not a view of the story."""


def _kept(text: str) -> str:
    return text if len(text) <= LIMIT else f"{text[:LIMIT]}\n\n[cut here: {len(text) - LIMIT} more characters]"


def _run_line(record: RunRecord) -> str:
    used = record.usage
    head = (
        f"- {record.role}, {record.phase.replace('_', ' ')}, round {record.attempt}: {record.outcome}, "
        f"model {record.model or 'default'}, {used.turns} turns, {used.seconds:.0f} s, ${used.cost_usd:.2f}"
    )
    calls = [
        f"    - {tool.name}: {tool.summary}{'' if tool.ok else f' (FAILED: {tool.note})'}" for tool in record.tools
    ]
    return "\n".join([head, *calls])


def render_story(  # noqa: PLR0913, PLR0917 - the parts a story is made of
    request: str,
    documents: Mapping[str, str],
    messages: Sequence[Message],
    runs: Sequence[RunRecord],
    dispute: str,
    ci: str,
) -> str:
    """The request, every document, the conversation between the agents, what each run did, the CI, and the dispute."""
    parts = ["# The whole story of this work", "", "## The request", "", _kept(request.strip()) or "(none)"]
    for name in (*DOCUMENT_ORDER, *sorted(set(documents) - set(DOCUMENT_ORDER))):
        if name in documents and name != "request.md":
            parts += ["", f"## {DOCUMENT_TITLES.get(name, name)} (`{name}`)", "", _kept(documents[name].strip())]
    parts += ["", "## The conversation, oldest first", ""]
    parts += [
        f"### {message.speaker} ({message.voice}) {message.when}\n\n{_kept(message.body.strip())}\n"
        for message in messages
    ] or ["(nothing yet)"]
    parts += ["", "## What each agent run did", ""]
    parts += [_run_line(record) for record in runs] or ["(no record)"]
    parts += ["", "## What the CI says now", "", ci.strip() or "(nothing to say)"]
    parts += ["", "## The dispute to settle", "", _kept(dispute.strip())]
    return "\n".join(parts) + "\n"
