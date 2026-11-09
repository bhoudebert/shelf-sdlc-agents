"""Signing in and seeing repositories, with the person's own token (the App's user-to-server flow)."""

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import Identity, PullInfo, RepoRef

NOT_FOUND = 404


class SignInError(Exception):
    """GitHub refused the OAuth code."""


def parse_identity(user: Mapping[str, Any], organisations: list[Mapping[str, Any]]) -> Identity:
    """Build an identity from GitHub's ``/user`` and ``/user/orgs`` answers."""
    return Identity(str(user["login"]), frozenset(str(org["login"]) for org in organisations))


def parse_repositories(payload: Mapping[str, Any]) -> list[RepoRef]:
    """Read the repositories of an ``/installations/{id}/repositories`` page."""
    return [RepoRef.parse(str(repo["full_name"])) for repo in payload.get("repositories", [])]


def pull_info(pull: Mapping[str, Any], repo: RepoRef) -> PullInfo:
    """Read what matters of a pull request from GitHub's answer; ``repo`` is where the pull request was asked for."""
    head: Mapping[str, Any] = pull.get("head") or {}
    origin: Mapping[str, Any] = head.get("repo") or {}
    return PullInfo(
        branch=str(head.get("ref") or ""),
        sha=str(head.get("sha") or ""),
        open=pull.get("state") == "open",
        same_repository=origin.get("full_name") == repo.full_name,
    )


@dataclass(frozen=True, slots=True)
class GitHubForge:
    """The ``Forge`` port over GitHub's REST API."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings

    async def exchange_code(self, code: str) -> str:
        """Trade the OAuth ``code`` for the person's user-to-server token."""
        response = await self.client.post(
            f"{self.settings.web_url}/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "code": code,
            },
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("access_token")
        if not token:
            raise SignInError(str(body.get("error_description") or body.get("error") or "no token returned"))
        return str(token)

    async def identity(self, user_token: str) -> Identity:
        """Who the token belongs to, and their organisations."""
        user = await self._get(user_token, "/user")
        organisations = [org async for org in self._pages(user_token, "/user/orgs")]
        return parse_identity(user, organisations)

    async def repositories(self, user_token: str) -> list[RepoRef]:
        """The repositories the App is installed on that this person can access."""
        found: list[RepoRef] = []
        async for installation in self._pages(user_token, "/user/installations", key="installations"):
            path = f"/user/installations/{installation['id']}/repositories"
            async for page in self._pages(user_token, path, key=None):
                found.extend(parse_repositories(page))
        return found

    async def pull_request(self, user_token: str, repo: RepoRef, number: int) -> PullInfo | None:
        """The pull request as this person sees it (asked as them, not as the App); ``None`` when there is none."""
        response = await self.client.get(
            f"{self.settings.api_url}/repos/{repo.full_name}/pulls/{number}", headers=_user_headers(user_token)
        )
        if response.status_code == NOT_FOUND:
            return None
        response.raise_for_status()
        return pull_info(response.json(), repo)

    async def _get(self, user_token: str, path: str) -> Mapping[str, Any]:
        response = await self.client.get(f"{self.settings.api_url}{path}", headers=_user_headers(user_token))
        response.raise_for_status()
        return response.json()

    async def _pages(self, user_token: str, path: str, key: str | None = None) -> AsyncIterator[Any]:
        """Follow ``Link: rel=next`` links. Yield each item of ``key`` (or each whole page when ``key`` is None)."""
        url: str | None = f"{self.settings.api_url}{path}?per_page=100"
        while url:
            response = await self.client.get(url, headers=_user_headers(user_token))
            response.raise_for_status()
            body = response.json()
            if key is None and isinstance(body, dict):
                yield body
            else:
                for item in body[key] if key else body:
                    yield item
            url = response.links.get("next", {}).get("url")


def _user_headers(user_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {user_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
