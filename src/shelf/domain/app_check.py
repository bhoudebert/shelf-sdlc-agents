"""Whether the GitHub App is set up the way this system needs, judged from what GitHub says about it. Pure."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto

REQUIRED_EVENTS: tuple[str, ...] = ("pull_request", "issue_comment")
"""The only events the web service reads: a pull request closed, a comment created."""

REQUIRED_PERMISSIONS: Mapping[str, str] = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "read",
    "actions": "read",
    "metadata": "read",
}
"""The repository permissions the system needs, at the least level that works."""

_LEVELS = {"none": 0, "read": 1, "write": 2, "admin": 3}
RECENT = 10
"""How many of the latest deliveries are weighed."""


class Level(StrEnum):
    """How much a finding matters."""

    OK = auto()
    WARNING = auto()
    ERROR = auto()


@dataclass(frozen=True, slots=True)
class Delivery:
    """What GitHub says about one webhook delivery."""

    event: str
    status_code: int
    at: datetime


@dataclass(frozen=True, slots=True)
class AppFacts:
    """What GitHub reports about the App and its webhook."""

    events: frozenset[str]
    permissions: Mapping[str, str]
    webhook_url: str
    webhook_secret_set: bool
    deliveries: Sequence[Delivery] = ()
    """Recent deliveries, in any order."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing found, and what to do about it."""

    level: Level
    title: str
    advice: str = ""


def delivered(code: int) -> bool:
    """Whether a delivery was answered with success."""
    return 200 <= code < 300  # noqa: PLR2004


def check_app(facts: AppFacts, expected_webhook_url: str) -> tuple[Finding, ...]:
    """Every finding about ``facts``, most serious first."""
    found = [
        _events(facts),
        _permissions(facts),
        _workflows(facts),
        _webhook_url(facts, expected_webhook_url),
        _secret(facts),
        *_deliveries(facts),
    ]
    order = {Level.ERROR: 0, Level.WARNING: 1, Level.OK: 2}
    return tuple(sorted(found, key=lambda finding: order[finding.level]))


def _events(facts: AppFacts) -> Finding:
    missing = [event for event in REQUIRED_EVENTS if event not in facts.events]
    if not missing:
        return Finding(Level.OK, "The App is subscribed to the events it needs (Pull request, Issue comment).")
    names = ", ".join(missing)
    return Finding(
        Level.ERROR,
        f"The App is not subscribed to: {names}.",
        "On the App's settings page, open Permissions & events, scroll to Subscribe to events and tick Pull request "
        "and Issue comment, then save. A box is greyed until its permission is granted (Pull requests, Issues), so "
        "set the permissions first. Until then GitHub sends nothing and commands on a pull request wait for the "
        "periodic check.",
    )


def _permissions(facts: AppFacts) -> Finding:
    short = [
        f"{name} ({wanted} needed, {facts.permissions.get(name, 'none')} granted)"
        for name, wanted in REQUIRED_PERMISSIONS.items()
        if _LEVELS.get(facts.permissions.get(name, "none"), 0) < _LEVELS[wanted]
    ]
    if not short:
        return Finding(Level.OK, "The App has the repository permissions it needs.")
    return Finding(
        Level.ERROR,
        "The App lacks permissions: " + ", ".join(short) + ".",
        "On the App's settings page, Permissions & events, set them, save, then accept the new permissions on each "
        "installation (GitHub emails the owner and shows a banner on the installation page).",
    )


def _workflows(facts: AppFacts) -> Finding:
    if _LEVELS.get(facts.permissions.get("workflows", "none"), 0) >= _LEVELS["write"]:
        return Finding(
            Level.OK,
            "Agents may change CI workflow files (the Workflows permission is granted).",
            "A changed workflow runs with the repository's secrets, so keep GitHub's own safeguards on: a CODEOWNERS "
            "line for .github/ with code-owner review required, environments with required reviewers for deploy "
            "secrets, and approval for workflows from forks. They apply to the agents' changes as to anyone's.",
        )
    return Finding(
        Level.OK,
        "Agents cannot change CI workflow files (the Workflows permission is not granted), which is the safe default.",
        "If a pull request needs to change .github/workflows, GitHub refuses the push. To allow it, set Workflows to "
        "Read and write under the App's Permissions & events, then accept it on each installation; or make that "
        "change by hand.",
    )


def _webhook_url(facts: AppFacts, expected: str) -> Finding:
    if facts.webhook_url.rstrip("/") == expected.rstrip("/"):
        return Finding(Level.OK, "The webhook URL is this instance's.")
    shown = facts.webhook_url or "none"
    return Finding(
        Level.ERROR,
        f"The webhook URL is {shown}, not {expected}.",
        "Set the Webhook URL on the App's settings page (General, Webhook) to the address above, and keep Active "
        "ticked.",
    )


def _secret(facts: AppFacts) -> Finding:
    if facts.webhook_secret_set:
        return Finding(Level.OK, "The App has a webhook secret.")
    return Finding(
        Level.ERROR,
        "The App has no webhook secret, so GitHub signs nothing and every webhook is refused.",
        "Set a Webhook secret on the App's settings page and the same value as GITHUB_WEBHOOK_SECRET in deploy/.env.",
    )


def _deliveries(facts: AppFacts) -> list[Finding]:
    recent = sorted(facts.deliveries, key=lambda delivery: delivery.at, reverse=True)[:RECENT]
    if not recent:
        return [
            Finding(
                Level.WARNING,
                "GitHub has not delivered any webhook lately.",
                "Comment on a pull request of a repository the App is installed on, then reload this page. If nothing "
                "appears, GitHub cannot reach the webhook URL: see Advanced, Recent deliveries on the App's page.",
            )
        ]
    latest = recent[0]
    failed = [delivery for delivery in recent if not delivered(delivery.status_code)]
    if delivered(latest.status_code):
        title = f"The latest delivery ({latest.event}) was answered {latest.status_code}."
        if failed:
            return [
                Finding(Level.OK, title),
                Finding(
                    Level.WARNING,
                    f"{len(failed)} of the last {len(recent)} deliveries failed.",
                    "Open Advanced, Recent deliveries on the App's page to see which, and redeliver them.",
                ),
            ]
        return [Finding(Level.OK, title)]
    return [
        Finding(
            Level.ERROR,
            f"The latest delivery ({latest.event}) failed: {_why(latest.status_code)}.",
            _fix(latest.status_code),
        )
    ]


def _why(code: int) -> str:
    if code in {401, 403}:
        return f"this instance answered {code}: the signature does not match"
    if code == 0:
        return "GitHub could not reach this instance (timed out or refused)"
    return f"this instance answered {code}"


def _fix(code: int) -> str:
    if code in {401, 403}:
        return (
            "The webhook secret on the App's page and GITHUB_WEBHOOK_SECRET in deploy/.env must be the same. "
            "Then redeliver."
        )
    if code == 0:
        return (
            "Check that the public address is reachable from the internet and that the reverse proxy forwards "
            "/api/github/webhook."
        )
    return "Read the instance's web log around that time: docker compose -f deploy/compose.yml logs web."
