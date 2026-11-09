"""One-click registration: the App manifest GitHub turns into a registered App, and the credentials it returns."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.app_check import REQUIRED_EVENTS, REQUIRED_PERMISSIONS

PERMISSIONS = dict(REQUIRED_PERMISSIONS)
EVENTS = list(REQUIRED_EVENTS)
"""The events to subscribe to: only the two the web service reads (a pull request closed, a comment created).

GitHub always sends ``installation``, ``installation_repositories`` and ``ping``; a manifest that lists them is refused.
"""


DESCRIPTION = """\
**Shelf SDLC Agents** lets your team drive AI agents on your repositories from a web board, \
from a need to a pull request.

**What it does**
- Runs agents at any step: spec, design, plan, implementation, review.
- Opens a draft pull request, reports every step on it and waits for the CI.
- Stops at the gates for a person: in the web board, or with `/shelf` commands on the pull request.

**What it may touch**
- Only the repositories it is installed on: it reads and writes code, pull requests and comments there, \
and reads CI runs and their logs.
- It cannot change workflow files unless the Workflows permission is granted.
- Its tokens last one hour and are minted per step.

**Who can use it:** only the people and organisations the operator of the instance lists. \
Signing in with GitHub proves who you are; it does not give access.

Self-hosted: each team runs its own instance. https://github.com/bhoudebert/shelf-sdlc-agents"""
"""The App's description (Markdown) for the Basic information pane: what it does, what it touches, who may use it."""


def app_manifest(public_url: str, name: str = "shelf-sdlc") -> dict[str, Any]:
    """The manifest to POST to ``/settings/apps/new``: URLs derived from the instance's public address."""
    base = public_url.rstrip("/")
    return {
        "name": name,
        "url": base,
        "redirect_url": f"{base}/setup/registered",
        "callback_urls": [f"{base}/auth/callback"],
        "setup_url": f"{base}/setup/installed",
        "setup_on_update": True,
        "hook_attributes": {"url": f"{base}/api/github/webhook", "active": True},
        "description": DESCRIPTION,
        "public": True,
        "request_oauth_on_install": False,
        "default_permissions": PERMISSIONS,
        "default_events": EVENTS,
    }


def registration_form(public_url: str, name: str = "shelf-sdlc", web_url: str = "https://github.com") -> str:
    """A page that posts the manifest to GitHub on load, which is how the browser starts the registration."""
    manifest = json.dumps(app_manifest(public_url, name)).replace("&", "&amp;").replace('"', "&quot;")
    return (
        f'<form id="f" method="post" action="{web_url}/settings/apps/new">'
        f'<input type="hidden" name="manifest" value="{manifest}"></form>'
        "<script>document.getElementById('f').submit()</script>"
    )


@dataclass(frozen=True, slots=True)
class Registered:
    """What GitHub returns once the person confirmed: the App's credentials, to put in the operator's environment."""

    app_id: str
    slug: str
    client_id: str
    client_secret: str
    webhook_secret: str
    private_key: str


async def convert(client: httpx.AsyncClient, code: str, api_url: str = "https://api.github.com") -> Registered:
    """Trade the temporary ``code`` from the registration redirect for the App's credentials."""
    response = await client.post(
        f"{api_url}/app-manifests/{code}/conversions", headers={"Accept": "application/vnd.github+json"}
    )
    response.raise_for_status()
    body = response.json()
    return Registered(
        app_id=str(body["id"]),
        slug=str(body["slug"]),
        client_id=str(body["client_id"]),
        client_secret=str(body["client_secret"]),
        webhook_secret=str(body["webhook_secret"]),
        private_key=str(body["pem"]),
    )


def settings_from(registered: Registered) -> GitHubAppSettings:
    """The runtime settings that a fresh registration implies."""
    return GitHubAppSettings(registered.app_id, registered.private_key, registered.client_id, registered.client_secret)
