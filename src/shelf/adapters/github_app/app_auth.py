"""The App's own identity: a short-lived JWT, traded for installation tokens that agents use for an hour."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import jwt

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef

JWT_LIFETIME = timedelta(minutes=9)
"""GitHub accepts at most ten minutes."""
CLOCK_SKEW = timedelta(seconds=30)


@dataclass(frozen=True, slots=True)
class InstallationToken:
    """A token scoped to an installation's repositories and the App's permissions."""

    value: str
    expires_at: datetime


def app_jwt(settings: GitHubAppSettings, now: datetime) -> str:
    """Sign the JWT that proves we are the App. ``now`` is passed in so the function stays pure."""
    claims = {
        "iat": int((now - CLOCK_SKEW).timestamp()),
        "exp": int((now + JWT_LIFETIME).timestamp()),
        "iss": settings.app_id,
    }
    return jwt.encode(claims, settings.private_key, algorithm="RS256")


def _headers(bearer: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def installation_id(client: httpx.AsyncClient, settings: GitHubAppSettings, repo: RepoRef, now: datetime) -> int:
    """The id of the installation covering ``repo``; raises ``httpx.HTTPStatusError`` if the App is not installed."""
    response = await client.get(
        f"{settings.api_url}/repos/{repo.full_name}/installation", headers=_headers(app_jwt(settings, now))
    )
    response.raise_for_status()
    return int(response.json()["id"])


async def installation_token(
    client: httpx.AsyncClient, settings: GitHubAppSettings, installation: int, now: datetime
) -> InstallationToken:
    """Mint an installation token. Valid for an hour; mint one per step and never store it."""
    response = await client.post(
        f"{settings.api_url}/app/installations/{installation}/access_tokens",
        headers=_headers(app_jwt(settings, now)),
    )
    response.raise_for_status()
    body = response.json()
    return InstallationToken(body["token"], datetime.fromisoformat(body["expires_at"]).astimezone(UTC))


def clone_url(repo: RepoRef, token: InstallationToken) -> str:
    """The HTTPS URL that clones ``repo`` as the App, with ``x-access-token`` authentication."""
    return f"https://x-access-token:{token.value}@github.com/{repo.full_name}.git"
