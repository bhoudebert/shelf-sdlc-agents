"""The title of a pull request: what the agent proposes, cleaned, or a fallback when it proposes nothing usable."""

import re

MAX_TITLE = 100
"""Longer than this is not a title; commit conventions usually cap the header at 72 to 100 characters."""

FALLBACK_LENGTH = 70
_PREFIX = re.compile(r"^\s*(?:pr\s+)?title\s*:\s*", re.IGNORECASE)


def fallback_title(request: str) -> str:
    """A title from the first line of the request, for when no better one is available."""
    first = next((line.strip() for line in request.splitlines() if line.strip()), "shelf work")
    return first[:FALLBACK_LENGTH]


SUMMARY_LENGTH = 90


def summary(text: str) -> str:
    """What a person reads on the board to tell one piece of work from another: the request's first line, shortened."""
    first = next(
        (line.strip().lstrip("#").strip() for line in text.splitlines() if line.strip().lstrip("#").strip()), ""
    )
    first = " ".join(first.split())
    return first if len(first) <= SUMMARY_LENGTH else first[: SUMMARY_LENGTH - 1].rstrip() + "…"


def clean_title(answer: str, fallback: str) -> str:
    """The title an agent answered: its last non-empty line without quotes, backticks or a ``Title:`` label.

    The ``fallback`` is returned when there is no line, or the line is too long to be a title.
    """
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    if not lines:
        return fallback
    title = _PREFIX.sub("", lines[-1]).strip().strip("`\"'*").strip()
    title = " ".join(title.split())
    return title if title and len(title) <= MAX_TITLE else fallback
