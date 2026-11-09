import httpx

from shelf.adapters.caching.conversation import CachedConversations
from shelf.adapters.github_app.conversation import GitHubConversations
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.domain.story import Message, Voice, agent_comment

REPO = RepoRef("acme", "shop")


def conversations(settings: GitHubAppSettings, comments: list[dict[str, object]]) -> GitHubConversations:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/acme/shop/issues/12/comments"
        return httpx.Response(200, json=comments)

    return GitHubConversations(httpx.AsyncClient(transport=httpx.MockTransport(handler)), settings, token_for)


def comment(body: str, login: str, when: str) -> dict[str, object]:
    return {"body": body, "user": {"login": login}, "created_at": when, "html_url": f"https://github.com/c/{when}"}


async def test_the_comments_become_a_story_without_the_progress_comment(settings: GitHubAppSettings) -> None:
    story = await conversations(
        settings,
        [
            comment(agent_comment("work-1", "implementer", "done"), "shelf[bot]", "t1"),
            comment("<!-- shelf-progress:work-1 -->\n### shelf-sdlc: progress\n\nrows", "shelf[bot]", "t2"),
            comment("nice", "carol", "t3"),
        ],
    ).read(REPO, 12)
    assert [(m.voice, m.speaker) for m in story] == [(Voice.AGENT, "Developer"), (Voice.PERSON, "carol")]
    assert story[1].url == "https://github.com/c/t3"


class Counting:
    def __init__(self) -> None:
        self.calls = 0

    async def read(self, repo: RepoRef, pull_request: int) -> list[Message]:
        self.calls += 1
        return []


async def test_a_conversation_is_remembered_for_a_few_seconds() -> None:
    inner, now = Counting(), [0.0]
    cached = CachedConversations(inner, ttl_seconds=10, clock=lambda: now[0])
    await cached.read(REPO, 12)
    await cached.read(REPO, 12)
    assert inner.calls == 1
    now[0] = 11.0
    await cached.read(REPO, 12)
    assert inner.calls == 2
