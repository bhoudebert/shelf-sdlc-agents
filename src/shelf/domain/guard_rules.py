"""The rules an administrator adds to the guard from the admin page: what is kept, and the overlay file it becomes."""

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum

from shelf.domain.guard import regex_of


class RuleKind(StrEnum):
    """What a rule does."""

    ALLOW_COMMAND = "allow_command"
    DENY_HOST = "deny_host"


@dataclass(frozen=True, slots=True)
class OverlayRule:
    """One rule added from the admin page."""

    id: str
    kind: RuleKind
    subject: str
    """The exact command to allow, or the host to deny."""
    by: str
    """The login of the administrator who added it."""
    at: str
    """When, ISO, UTC."""


MAX_COMMAND = 300
_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
_LOGIN = re.compile(r"[A-Za-z0-9-]{1,39}")


def _id(kind: RuleKind, subject: str) -> str:
    digest = hashlib.sha256(f"{kind.value}\0{subject}".encode()).hexdigest()[:10]
    return f"ui-{digest}"


def is_valid_host(host: str) -> bool:
    """Whether ``host`` is a plain host name: letters, digits, dots and hyphens, nothing a policy file could trip on."""
    return bool(_HOST.fullmatch(host))


def allow_command(command: str, by: str, at: str) -> OverlayRule | None:
    """A rule that allows exactly ``command``; ``None`` when the command or the login cannot be put in a policy file."""
    if not command or len(command) > MAX_COMMAND or "\n" in command or "\r" in command or not _LOGIN.fullmatch(by):
        return None
    return OverlayRule(_id(RuleKind.ALLOW_COMMAND, command), RuleKind.ALLOW_COMMAND, command, by, at)


def deny_host(host: str, by: str, at: str) -> OverlayRule | None:
    """A rule that denies ``host``; ``None`` when it is not a plain host name or the login is odd."""
    host = host.strip().lower()
    if not is_valid_host(host) or not _LOGIN.fullmatch(by):
        return None
    return OverlayRule(_id(RuleKind.DENY_HOST, host), RuleKind.DENY_HOST, host, by, at)


def _quoted(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(rules: tuple[OverlayRule, ...]) -> str:
    """The overlay file for ``rules``: a rule per allowed command, and the denied hosts in one list.

    The guard reads only this file, and only rules and denied domains from it. Each rule says who added it and when.
    """
    lines = [
        "# Written by the admin page of Shelf. Do not edit: the page rewrites this file as a whole.",
        "version = 1",
        "",
    ]
    for rule in rules:
        if rule.kind is RuleKind.ALLOW_COMMAND:
            lines += [
                "[[rules]]",
                f"id = {_quoted(rule.id)}",
                f"match = '^{regex_of(rule.subject)}$'",
                'decision = "allow"',
                f"reason = {_quoted(f'allowed by {rule.by} on {rule.at[:10]}')}",
                "",
            ]
    hosts = [rule.subject for rule in rules if rule.kind is RuleKind.DENY_HOST]
    if hosts:
        lines += ["[network]", f"deny_domains = [{', '.join(_quoted(host) for host in hosts)}]", ""]
    return "\n".join(lines)
