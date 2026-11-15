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
    ALLOW_SITE = "allow_site"
    ALLOW_FILE = "allow_file"


@dataclass(frozen=True, slots=True)
class OverlayRule:
    """One rule added from the admin page."""

    id: str
    kind: RuleKind
    subject: str
    """The exact command to allow, the host to deny, or the site a sandboxed command may reach."""
    by: str
    """The login of the administrator who added it."""
    at: str
    """When, ISO, UTC."""


FREEABLE_FILES: dict[str, str] = {
    "**/opencode.json": "opencode.json (OpenCode's project configuration)",
    "**/opencode.jsonc": "opencode.jsonc (OpenCode's project configuration)",
    "**/.opencode/**": "the .opencode folder (OpenCode's plugins and agents)",
    "**/.codex/**": "the .codex folder (Codex's project configuration)",
    "**/.github/copilot/**": "the .github/copilot folder (Copilot's project configuration)",
    "**/.github/hooks/**": "the .github/hooks folder (hooks of Copilot's agent)",
}
"""The project agent files an administrator may free for the agents' writes, and how the page names them.

Warden honours this list and nothing else: the settings and hooks of Claude Code, its own files and the git hooks are
never in it."""

MAX_COMMAND = 300
_HOST = re.compile(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?")
_LABEL_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
MAX_SITE = 253
MAX_LABEL = 63
MIN_LABELS = 2
MIN_TOP_LEVEL = 2
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


def _is_label(label: str) -> bool:
    """One part of a host name: letters, digits and hyphens, not starting or ending with a hyphen."""
    return (
        0 < len(label) <= MAX_LABEL
        and not label.startswith("-")
        and not label.endswith("-")
        and all(char in _LABEL_CHARS for char in label)
    )


def is_valid_site(site: str) -> bool:
    """Whether ``site`` is a public host name, or ``*.`` and a domain of two labels at least; nothing else.

    No address, no name without a dot, no scheme, port or path, no wildcard over a whole top-level domain. It is checked
    label by label, with no regular expression, because the text comes from a form.
    """
    if not site or len(site) > MAX_SITE:
        return False
    labels = site.removeprefix("*.").split(".")
    top = labels[-1]
    return (
        len(labels) >= MIN_LABELS
        and all(_is_label(label) for label in labels)
        and len(top) >= MIN_TOP_LEVEL
        and top.isascii()
        and top.isalpha()
    )


def allow_site(site: str, by: str, at: str) -> OverlayRule | None:
    """A rule that lets a sandboxed command reach ``site``; ``None`` when it is not a valid site or the login is odd."""
    site = site.strip().lower()
    if not is_valid_site(site) or not _LOGIN.fullmatch(by):
        return None
    return OverlayRule(_id(RuleKind.ALLOW_SITE, site), RuleKind.ALLOW_SITE, site, by, at)


def allow_file(pattern: str, by: str, at: str) -> OverlayRule | None:
    """A rule that frees a project agent file for the agents' writes; ``None`` for what is not in ``FREEABLE_FILES``."""
    if pattern not in FREEABLE_FILES or not _LOGIN.fullmatch(by):
        return None
    return OverlayRule(_id(RuleKind.ALLOW_FILE, pattern), RuleKind.ALLOW_FILE, pattern, by, at)


def allowed_sites(rules: tuple[OverlayRule, ...]) -> tuple[str, ...]:
    """The sites a sandboxed command may reach because of ``rules``, in the order they were added."""
    return tuple(rule.subject for rule in rules if rule.kind is RuleKind.ALLOW_SITE)


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
    freed = [rule.subject for rule in rules if rule.kind is RuleKind.ALLOW_FILE]
    if freed:
        lines += ["[paths]", f"unprotect = [{', '.join(_quoted(pattern) for pattern in freed)}]", ""]
    hosts = [rule.subject for rule in rules if rule.kind is RuleKind.DENY_HOST]
    if hosts:
        lines += ["[network]", f"deny_domains = [{', '.join(_quoted(host) for host in hosts)}]", ""]
    return "\n".join(lines)
