"""GitHub webhooks: verify the signature, then say which piece of work an event is about."""

import hashlib
import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from shelf.domain.commands import MARKER, parse_command
from shelf.domain.model import WorkId
from shelf.domain.work import DecisionKind

TRUSTED = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
_MARKER = re.compile(re.escape(MARKER) + r"(work-[0-9a-f]+) -->")
_BRANCH = re.compile(r"^shelf/(work-[0-9a-f]+)$")


def valid_signature(secret: str, body: bytes, header: str | None) -> bool:
    """Whether ``header`` (``sha256=<hex>``) is the HMAC of ``body`` under ``secret``."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


@dataclass(frozen=True, slots=True)
class Closed:
    """The pull request of a piece of work was merged or closed."""

    work_id: WorkId
    merged: bool


@dataclass(frozen=True, slots=True)
class Commented:
    """A trusted person typed a command on the pull request of a piece of work."""

    work_id: WorkId
    login: str
    kind: DecisionKind
    note: str


def work_id_of(body: str | None) -> WorkId | None:
    """The work id the factory left in a pull request's body, if it is one of ours."""
    found = _MARKER.search(body or "")
    return WorkId(found.group(1)) if found else None


def interpret(event: str, payload: Mapping[str, Any]) -> Closed | Commented | None:
    """What a webhook means for us; ``None`` for everything we do not act on."""
    if event == "pull_request" and payload.get("action") == "closed":
        pull = payload.get("pull_request", {})
        branch = _BRANCH.match(str(pull.get("head", {}).get("ref", "")))
        work_id = WorkId(branch.group(1)) if branch else work_id_of(pull.get("body"))
        return Closed(work_id, bool(pull.get("merged"))) if work_id else None
    if event == "issue_comment" and payload.get("action") == "created":
        issue, comment = payload.get("issue", {}), payload.get("comment", {})
        work_id = work_id_of(issue.get("body")) if "pull_request" in issue else None
        command = parse_command(str(comment.get("body", "")))
        if work_id and command and comment.get("author_association") in TRUSTED:
            return Commented(work_id, str(comment["user"]["login"]), *command)
    return None
