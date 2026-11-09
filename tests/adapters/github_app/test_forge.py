import httpx
import pytest

from shelf.adapters.github_app.forge import GitHubForge, SignInError, parse_identity, parse_repositories
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import Identity, RepoRef


def forge_over(handler: httpx.MockTransport, settings: GitHubAppSettings) -> GitHubForge:
    return GitHubForge(httpx.AsyncClient(transport=handler), settings)


def test_an_identity_is_read_from_the_user_and_their_organisations() -> None:
    assert parse_identity({"login": "alice"}, [{"login": "acme"}]) == Identity("alice", frozenset({"acme"}))


def test_repositories_are_read_from_an_installation_page() -> None:
    page = {"repositories": [{"full_name": "acme/shop"}, {"full_name": "acme/api"}]}
    assert parse_repositories(page) == [RepoRef("acme", "shop"), RepoRef("acme", "api")]


async def test_the_oauth_code_is_traded_for_a_token(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/login/oauth/access_token"
        assert b"code=abc" in request.content
        return httpx.Response(200, json={"access_token": "ghu_1"})

    assert await forge_over(httpx.MockTransport(handler), settings).exchange_code("abc") == "ghu_1"


async def test_a_refused_code_raises_with_githubs_reason(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "bad_verification_code", "error_description": "The code is wrong"})

    with pytest.raises(SignInError, match="The code is wrong"):
        await forge_over(httpx.MockTransport(handler), settings).exchange_code("nope")


async def test_the_identity_includes_the_organisations(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer ghu_1"
        if request.url.path == "/user":
            return httpx.Response(200, json={"login": "alice"})
        return httpx.Response(200, json=[{"login": "acme"}, {"login": "globex"}])

    identity = await forge_over(httpx.MockTransport(handler), settings).identity("ghu_1")
    assert identity == Identity("alice", frozenset({"acme", "globex"}))


async def test_repositories_are_collected_across_installations_and_pages(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/user/installations":
            return httpx.Response(200, json={"installations": [{"id": 1}, {"id": 2}]})
        if path == "/user/installations/1/repositories" and "page=2" not in str(request.url):
            link = '<https://api.github.com/user/installations/1/repositories?per_page=100&page=2>; rel="next"'
            return httpx.Response(200, json={"repositories": [{"full_name": "acme/a"}]}, headers={"Link": link})
        if path == "/user/installations/1/repositories":
            return httpx.Response(200, json={"repositories": [{"full_name": "acme/b"}]})
        return httpx.Response(200, json={"repositories": [{"full_name": "globex/c"}]})

    repos = await forge_over(httpx.MockTransport(handler), settings).repositories("ghu_1")
    assert repos == [RepoRef("acme", "a"), RepoRef("acme", "b"), RepoRef("globex", "c")]


@pytest.mark.parametrize(("status", "expected"), [(200, True), (404, False)])
async def test_a_pull_request_exists_when_the_person_can_read_it(
    settings: GitHubAppSettings,
    status: int,
    expected: bool,  # noqa: FBT001
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/pulls/2"
        assert request.headers["authorization"] == "Bearer ghu_1"  # as the person, not as the App
        return httpx.Response(status, json={})

    forge = forge_over(httpx.MockTransport(handler), settings)
    assert await forge.pull_request_exists("ghu_1", RepoRef("acme", "shop"), 2) is expected
