"""Existing material a piece of work can start from: an issue or pull request, or a file of the repository."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from shelf.domain.model import RepoRef
from shelf.domain.result import Err, Ok, Result

MAX_BYTES = 100_000
"""The most text that is taken from one reference; a longer document is better pointed at than pasted into a prompt."""

MAX_PATH = 200
MIN_SEGMENTS = 4
"""An address of this kind has an owner, a repository, a kind and something after it."""
MIN_BLOB = 2
"""A file address has a branch and at least one part of a path after ``blob``."""
TRUSTED_AUTHORS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
"""Only people with write access: whatever an outsider wrote must never steer the agents."""

MAX_REFERENCE = 500
"""The longest reference that is looked at: an address or a path is short, and nothing longer is worth parsing."""

_NUMBER = re.compile(r"#?[0-9]{1,9}")


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

    Only this repository is accepted: the App reads what it is installed on, and no other address is followed. Addresses
    are split into their parts, never matched with a pattern, so nothing a person types can make this slow.
    """
    given = text.strip()
    if len(given) > MAX_REFERENCE:
        return Err("that reference is too long to be an issue, a pull request or a path")
    if _NUMBER.fullmatch(given):
        return Ok(Thread(int(given.lstrip("#"))))
    if "://" in given:
        return _address(given, repo)
    return _file(given)


def _address(given: str, repo: RepoRef) -> Result[Reference, str]:
    """An address on GitHub: an issue, a pull request or a file of this repository."""
    parts = urlsplit(given)
    segments = [segment for segment in parts.path.split("/") if segment]
    if parts.scheme != "https" or parts.netloc.lower() != "github.com" or len(segments) < MIN_SEGMENTS:
        return Err("only an address on GitHub that belongs to this repository can be followed")
    wrong = _elsewhere(repo, segments[0], segments[1])
    if wrong:
        return Err(wrong)
    kind, rest = segments[2], segments[3:]
    if kind in ("issues", "pull") and len(rest) == 1 and rest[0].isdigit():
        return Ok(Thread(int(rest[0])))
    if kind == "blob" and len(rest) >= MIN_BLOB:
        return _file("/".join(rest[1:]), rest[0])
    return Err("that address is not an issue, a pull request or a file")


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
