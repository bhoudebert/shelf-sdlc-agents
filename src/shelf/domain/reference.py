"""Existing material a piece of work can start from: an issue or pull request, or a file of the repository."""

import re
from dataclasses import dataclass

from shelf.domain.model import RepoRef
from shelf.domain.result import Err, Ok, Result

MAX_BYTES = 100_000
"""The most text that is taken from one reference; a longer document is better pointed at than pasted into a prompt."""

MAX_PATH = 200
TRUSTED_AUTHORS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
"""Only people with write access: whatever an outsider wrote must never steer the agents."""

_NUMBER = re.compile(r"^#?(\d+)$")
_THREAD = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/(?:issues|pull)/(\d+)/?(?:[#?].*)?$")
_BLOB = re.compile(r"^https://github\.com/([\w.-]+)/([\w.-]+)/blob/([^/]+)/(.+?)(?:[#?].*)?$")


@dataclass(frozen=True, slots=True)
class Thread:
    """An issue or a pull request of the repository, read for what it says."""

    number: int


@dataclass(frozen=True, slots=True)
class File:
    """A file of the repository, at ``ref`` (its default branch when empty)."""

    path: str
    ref: str = ""


type Reference = Thread | File


@dataclass(frozen=True, slots=True)
class Imported:
    """What was read from a reference: where it came from, and its text."""

    source: str
    text: str


def parse_reference(text: str, repo: RepoRef) -> Result[Reference, str]:
    """Read what a person typed: ``#12``, an issue or pull request address, a file's address, or a path.

    Only this repository is accepted: the App reads what it is installed on, and no other address is followed.
    """
    given = text.strip()
    if found := _NUMBER.match(given):
        return Ok(Thread(int(found.group(1))))
    if found := _THREAD.match(given):
        wrong = _elsewhere(repo, found.group(1), found.group(2))
        return Err(wrong) if wrong else Ok(Thread(int(found.group(3))))
    if found := _BLOB.match(given):
        wrong = _elsewhere(repo, found.group(1), found.group(2))
        return Err(wrong) if wrong else _file(found.group(4), found.group(3))
    if "://" in given:
        return Err("only an address on GitHub that belongs to this repository can be followed")
    return _file(given)


def _elsewhere(repo: RepoRef, owner: str, name: str) -> str:
    """Why an address is refused when it belongs to another repository; nothing when it is this one's."""
    if (owner.lower(), name.lower()) == (repo.owner.lower(), repo.name.lower()):
        return ""
    return f"that address belongs to {owner}/{name}, not to {repo.full_name}"


def _file(path: str, ref: str = "") -> Result[Reference, str]:
    clean = path.strip()
    parts = clean.split("/")
    if not clean or clean.startswith("/") or "\\" in clean or ".." in parts or len(clean) > MAX_PATH:
        return Err("a file is given as a path inside the repository, such as docs/specs/loyalty.md")
    return Ok(File(clean, ref))


def combine(imported: Imported, typed: str) -> str:
    """The text a work starts from: what was imported, said where from, then what the requester added, if anything."""
    text = f"> Imported from {imported.source}\n\n{imported.text.strip()}"
    if typed.strip():
        text += f"\n\n---\n\nNote from the requester:\n\n{typed.strip()}"
    return text + "\n"
