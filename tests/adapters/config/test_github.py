import httpx
import pytest

from shelf.adapters.config.github import GitHubRepoConfigs
from shelf.domain.config import InvalidConfigError, RepoConfig
from shelf.domain.model import RepoRef

API = "https://api.github.com"
REPO = RepoRef("acme", "shop")


def configs(handler: httpx.MockTransport) -> GitHubRepoConfigs:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    return GitHubRepoConfigs(httpx.AsyncClient(transport=handler), API, token_for)


async def test_a_repository_without_a_file_gets_the_defaults() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    assert await configs(transport).load(REPO) == RepoConfig()


async def test_the_file_is_fetched_raw_with_the_apps_token_and_parsed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/contents/.shelf/config.toml"
        assert request.headers["Accept"] == "application/vnd.github.raw+json"
        assert request.headers["Authorization"] == "Bearer ghs_token"
        return httpx.Response(200, text='base_branch = "develop"\n[policy]\nmax_rounds = 2\n')

    config = await configs(httpx.MockTransport(handler)).load(REPO)
    assert (config.base_branch, config.policy.max_rounds) == ("develop", 2)


async def test_an_invalid_file_is_an_error_not_silent_defaults() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text="[policy]\nrounds = 2\n"))
    with pytest.raises(InvalidConfigError, match="unknown keys"):
        await configs(transport).load(REPO)
