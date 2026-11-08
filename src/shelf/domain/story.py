"""The story of a piece of work: the conversation on its pull request, where agents and people talk like a team.

Every comment the system posts carries a hidden marker saying who is speaking, so the pull request and the interface can
both read the conversation back and tell an agent from a person.
"""

from dataclasses import dataclass
from enum import StrEnum, auto

AGENT_MARK = "<!-- shelf-agent:"
PERSON_MARK = "<!-- shelf-person:"
PROGRESS_MARK = "<!-- shelf-progress:"

SPEAKERS: dict[str, str] = {
    "intake": "Spec writer",
    "spec_critic": "Spec reviewer",
    "architect": "Architect",
    "design_reviewer": "Design reviewer",
    "planner": "Planner",
    "implementer": "Developer",
    "code_reviewer": "Code reviewer",
    "checks": "Checks",
}
"""The agents as the people they stand in for, by role name."""


class Voice(StrEnum):
    """Who is speaking."""

    AGENT = auto()
    PERSON = auto()
    SUMMARY = auto()
    OTHER = auto()


@dataclass(frozen=True, slots=True)
class Message:
    """One comment of the story, read back."""

    voice: Voice
    speaker: str
    body: str
    when: str = ""
    url: str = ""


def agent_comment(work_id: str, role: str, body: str) -> str:
    """A comment spoken by an agent: marked, and headed with who it is."""
    title = SPEAKERS.get(role, role)
    return f"{AGENT_MARK}{role}:{work_id} -->\n**{title}** · agent\n\n{body}".strip()


def person_comment(work_id: str, login: str, body: str) -> str:
    """A comment a person made from the interface, posted by the App on their behalf and attributed to them."""
    return f"{PERSON_MARK}{login}:{work_id} -->\n**{login}** · via shelf\n\n{body}".strip()


def classify(body: str, author: str, when: str = "", url: str = "") -> Message:
    """Read a pull request comment back into the story: an agent, a person (here or on GitHub), or the progress."""
    if PROGRESS_MARK in body:
        return Message(Voice.SUMMARY, "Progress", body, when, url)
    if body.startswith(AGENT_MARK):
        role = body[len(AGENT_MARK) :].split(":", 1)[0]
        return Message(Voice.AGENT, SPEAKERS.get(role, role), _after_header(body), when, url)
    if body.startswith(PERSON_MARK):
        login = body[len(PERSON_MARK) :].split(":", 1)[0]
        return Message(Voice.PERSON, login, _after_header(body), when, url)
    return Message(Voice.PERSON if not author.endswith("[bot]") else Voice.OTHER, author, body, when, url)


def _after_header(body: str) -> str:
    """The comment without its marker line and its speaker header."""
    lines = body.split("\n")
    return "\n".join(lines[3:]).strip() if len(lines) > 3 else ""  # noqa: PLR2004 - marker, header, blank line
