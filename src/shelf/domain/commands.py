"""The `/shelf` commands people type on a pull request. A closed list matched by word, never interpreted by a model."""

from shelf.domain.work import DecisionKind

PREFIX = "/shelf"
WORDS: dict[str, DecisionKind] = {
    "approve": DecisionKind.APPROVE,
    "changes": DecisionKind.CHANGES,
    "resume": DecisionKind.RESUME,
    "reject": DecisionKind.REJECT,
    "abort": DecisionKind.ABORT,
}
HELP = (
    "Reply with `/shelf approve`, `/shelf changes <what to change>`, `/shelf resume [note]`, "
    "`/shelf reject` or `/shelf abort`."
)
MARKER = "<!-- shelf:"


def parse_command(body: str) -> tuple[DecisionKind, str] | None:
    """Read a comment: the first line must start with ``/shelf`` and a known word; the rest is the note."""
    lines = body.strip().splitlines()
    if not lines:
        return None
    words = lines[0].split(maxsplit=2)
    if len(words) < 2 or words[0] != PREFIX or words[1].lower() not in WORDS:  # noqa: PLR2004
        return None
    first_note = words[2] if len(words) > 2 else ""  # noqa: PLR2004
    note = "\n".join([first_note, *lines[1:]]).strip()
    return WORDS[words[1].lower()], note


def is_ours(body: str) -> bool:
    """Whether a comment was posted by the factory itself, which never reads its own comments."""
    return MARKER in body
