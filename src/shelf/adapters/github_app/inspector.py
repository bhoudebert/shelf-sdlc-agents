"""Look at the App itself on GitHub, as the App, to say whether it is set up right."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from shelf.adapters.github_app.app_auth import app_jwt
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.app_check import AppFacts, Delivery
from shelf.domain.result import Err, Ok, Result


@dataclass(frozen=True, slots=True)
class GitHubAppInspector:
    """Reads ``/app``, the webhook configuration and its recent deliveries with the App's own identity."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    async def facts(self) -> Result[AppFacts, str]:
        """The App's configuration, or a sentence saying why it could not be read."""
        headers = {
            "Authorization": f"Bearer {app_jwt(self.settings, self.clock())}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        base = self.settings.api_url
        try:
            app = await self._get(f"{base}/app", headers)
            hook = await self._get(f"{base}/app/hook/config", headers)
            deliveries = await self._get(f"{base}/app/hook/deliveries?per_page=20", headers)
        except httpx.HTTPStatusError as error:
            return Err(_refusal(error.response.status_code))
        except httpx.HTTPError as error:
            return Err(f"GitHub could not be reached ({type(error).__name__}).")
        return Ok(
            AppFacts(
                events=frozenset(str(event) for event in app.get("events", [])),
                permissions={str(name): str(level) for name, level in app.get("permissions", {}).items()},
                webhook_url=str(hook.get("url") or ""),
                webhook_secret_set=bool(hook.get("secret")),
                deliveries=tuple(_delivery(item) for item in deliveries),
            )
        )

    async def _get(self, url: str, headers: dict[str, str]) -> Any:  # noqa: ANN401 - GitHub's JSON, read by the caller
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def _delivery(item: dict[str, Any]) -> Delivery:
    return Delivery(
        event=str(item.get("event", "")),
        status_code=int(item.get("status_code") or 0),
        at=datetime.fromisoformat(str(item["delivered_at"])),
    )


def _refusal(status: int) -> str:
    if status in {401, 403}:
        return (
            f"GitHub refused the App's identity ({status}): GITHUB_APP_ID and the private key in deploy/ do not belong "
            "to the same App."
        )
    return f"GitHub answered {status} when asked about the App."
