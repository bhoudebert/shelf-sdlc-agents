from datetime import UTC, datetime

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from shelf.adapters.github_app.app_auth import (
    InstallationToken,
    app_jwt,
    clone_url,
    installation_id,
    installation_token,
)
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
REPO = RepoRef("acme", "shop")


def test_the_app_jwt_is_signed_with_the_private_key_and_expires_within_ten_minutes(
    settings: GitHubAppSettings, private_key: rsa.RSAPrivateKey
) -> None:
    token = app_jwt(settings, NOW)
    claims = jwt.decode(
        token, private_key.public_key(), algorithms=["RS256"], options={"verify_exp": False, "verify_iat": False}
    )
    assert claims["iss"] == "123"
    assert claims["exp"] - claims["iat"] <= 600 + 30


async def test_the_installation_of_a_repository_is_found_with_the_app_jwt(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/installation"
        assert request.headers["Authorization"].startswith("Bearer ey")
        return httpx.Response(200, json={"id": 42})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await installation_id(client, settings, REPO, NOW) == 42


async def test_an_installation_token_is_minted_and_parsed(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/app/installations/42/access_tokens"
        return httpx.Response(201, json={"token": "ghs_abc", "expires_at": "2026-11-08T13:00:00Z"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        token = await installation_token(client, settings, 42, NOW)
    assert token == InstallationToken("ghs_abc", datetime(2026, 11, 8, 13, 0, tzinfo=UTC))


def test_the_clone_url_authenticates_as_the_app() -> None:
    url = clone_url(REPO, InstallationToken("ghs_abc", NOW))
    assert url == "https://x-access-token:ghs_abc@github.com/acme/shop.git"
