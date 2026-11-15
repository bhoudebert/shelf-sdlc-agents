"""How deep the reviews of a document look, and what the reviewer is told about it."""

from enum import StrEnum

from shelf.domain.pipeline import Phase


class ReviewDepth(StrEnum):
    """How hard the spec and design reviews look: from what would stop the work, to everything that could go wrong."""

    QUICK = "quick"
    STANDARD = "standard"
    THOROUGH = "thorough"


DOCUMENT_REVIEWS = frozenset({Phase.SPEC_REVIEW, Phase.DESIGN_REVIEW})
"""The reviews of documents. The code review judges correctness and is never turned down."""

_QUICK = (
    "This is a quick review, and this replaces the limit of problems above. Read once. Report only the problems that "
    "would stop the work from being built or tested, at most three. Do not look for edge cases the request did not "
    "raise. If a team could build from the document, approve it."
)
_THOROUGH = (
    "This is a thorough review, and this replaces the limit of problems above. Look hard at edge cases, failure modes, "
    "what is missing, what is vague and what contradicts something that already exists, up to ten problems, most "
    "serious first. Scope beyond the request is still a problem to remove, not a gap to fill."
)


def review_note(depth: ReviewDepth, phase: Phase) -> str:
    """What the reviewer of ``phase`` is told about its depth; empty for the standard depth and for other phases."""
    if phase not in DOCUMENT_REVIEWS:
        return ""
    match depth:
        case ReviewDepth.QUICK:
            return _QUICK
        case ReviewDepth.THOROUGH:
            return _THOROUGH
        case ReviewDepth.STANDARD:
            return ""
