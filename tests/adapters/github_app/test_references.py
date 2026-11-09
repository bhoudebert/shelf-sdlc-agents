import httpx

from shelf.adapters.github_app.references import GitHubReferences
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.domain.reference import MAX_BYTES, File, Imported, Thread
from shelf.domain.result import Err, Ok

REPO = RepoRef("acme", "shop")


def references(settings: GitHubAppSettings, handler: httpx.MockTransport) -> GitHubReferences:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    return GitHubReferences(httpx.AsyncClient(transport=handler), settings, token_for)


def issue(association: str, title: str = "Loyalty", body: str | None = "Points at checkout") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/issues/42"
        return httpx.Response(200, json={"title": title, "body": body, "author_association": association})

    return httpx.MockTransport(handler)


async def test_an_issue_written_by_someone_with_write_access_becomes_the_request(settings: GitHubAppSettings) -> None:
    result = await references(settings, issue("MEMBER")).read(REPO, Thread(42))
    assert result == Ok(Imported("#42", "# Loyalty\n\nPoints at checkout"))


async def test_an_issue_written_by_an_outsider_never_steers_the_agents(settings: GitHubAppSettings) -> None:
    for association in ("NONE", "CONTRIBUTOR", "FIRST_TIME_CONTRIBUTOR"):
        result = await references(settings, issue(association)).read(REPO, Thread(42))
        assert isinstance(result, Err)
        assert "without write access" in result.error


async def test_an_issue_that_does_not_exist_is_said(settings: GitHubAppSettings) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={}))
    assert await references(settings, transport).read(REPO, Thread(42)) == Err(
        "acme/shop has no issue or pull request #42"
    )


async def test_an_issue_with_no_body_is_just_its_title(settings: GitHubAppSettings) -> None:
    result = await references(settings, issue("OWNER", body=None)).read(REPO, Thread(42))
    assert result == Ok(Imported("#42", "# Loyalty\n\n"))


def contents(status: int, content: bytes = b"", content_type: str = "text/plain") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/contents/docs/spec.md"
        assert request.headers["accept"] == "application/vnd.github.raw+json"
        return httpx.Response(status, content=content, headers={"content-type": content_type})

    return httpx.MockTransport(handler)


async def test_a_file_is_read_from_the_default_branch_or_the_given_one(settings: GitHubAppSettings) -> None:
    result = await references(settings, contents(200, b"# Spec\n")).read(REPO, File("docs/spec.md"))
    assert result == Ok(Imported("docs/spec.md", "# Spec\n"))


async def test_the_branch_of_a_file_address_is_sent(settings: GitHubAppSettings) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url.params))
        return httpx.Response(200, content=b"x")

    await references(settings, httpx.MockTransport(handler)).read(REPO, File("a.md", "v1"))
    assert seen == ["ref=v1"]


async def test_a_missing_file_a_folder_a_big_file_and_a_binary_one_are_each_said(settings: GitHubAppSettings) -> None:
    missing = await references(settings, contents(404)).read(REPO, File("docs/spec.md"))
    folder = await references(settings, contents(200, b"[]", "application/json")).read(REPO, File("docs/spec.md"))
    big = await references(settings, contents(200, b"x" * (MAX_BYTES + 1))).read(REPO, File("docs/spec.md"))
    binary = await references(settings, contents(200, b"\xff\xfe\x00")).read(REPO, File("docs/spec.md"))
    assert missing == Err("acme/shop has no file docs/spec.md on the default branch")
    assert isinstance(folder, Err)
    assert "is a folder" in folder.error
    assert isinstance(big, Err)
    assert "longer than" in big.error
    assert isinstance(binary, Err)
    assert "not a text file" in binary.error
