import httpx

from shelf.adapters.github_app.documents import GitHubDocuments
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef, WorkId

REPO = RepoRef("acme", "shop")


def documents(settings: GitHubAppSettings, handler: httpx.MockTransport) -> GitHubDocuments:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    return GitHubDocuments(httpx.AsyncClient(transport=handler), settings, token_for)


async def test_the_documents_that_exist_are_read_from_the_works_branch(settings: GitHubAppSettings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/spec.md"):
            return httpx.Response(200, text="# Spec\n")
        if request.url.path.endswith("/request.md"):
            return httpx.Response(200, text="loyalty points\n")
        return httpx.Response(404)

    found = await documents(settings, httpx.MockTransport(handler)).read(REPO, WorkId("work-1"))
    assert found == {"request.md": "loyalty points\n", "spec.md": "# Spec\n"}
    assert all(r.url.params["ref"] == "shelf/work-1" for r in seen)
    assert all(r.headers["Accept"] == "application/vnd.github.raw+json" for r in seen)
    assert {r.url.path for r in seen} >= {"/repos/acme/shop/contents/docs/shelf/work-1/spec.md"}


async def test_a_work_with_nothing_written_has_no_documents(settings: GitHubAppSettings) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    assert await documents(settings, transport).read(REPO, WorkId("work-1")) == {}
