"""One-click registration: the App manifest GitHub turns into a registered App, and the credentials it returns."""

import json
from dataclasses import dataclass
from typing import Any

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings

PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "read",
    "metadata": "read",
}
EVENTS = [
    "pull_request",
    "issue_comment",
    "check_suite",
    "installation",
    "installation_repositories",
    "push",
]


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
        "public": False,
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
