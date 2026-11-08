import json

import httpx
import pytest

from shelf.adapters.github_app.pulls import GitHubPullRequests, announcement, events_from, title_of
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.work import AskPerson, DecisionKind, PersonDecided, PullRequestClosed, Reason

REPO = RepoRef("acme", "shop")
NEED = WorkContext(WorkId("work-1"), WorkRequest(REPO, "alice", EntryPoint.NEED, "Loyalty points\nmore detail"))
REVIEW = WorkContext(WorkId("work-2"), WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, pull_request=7))


def adapter(settings: GitHubAppSettings, handler: httpx.MockTransport) -> GitHubPullRequests:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    async def base(repo: RepoRef) -> str:
        return "main"

    return GitHubPullRequests(httpx.AsyncClient(transport=handler), settings, token_for, base)


def comment(identifier: int, body: str, login: str = "bob", association: str = "MEMBER") -> dict[str, object]:
    return {"id": identifier, "body": body, "user": {"login": login}, "author_association": association}


def test_the_title_is_the_first_non_empty_line_cut_to_fit() -> None:
    assert title_of("\n\n  Loyalty points  \nmore") == "Loyalty points"
    assert len(title_of("x" * 200)) == 70
    assert title_of("  ") == "shelf work"


def test_an_announcement_says_what_is_awaited_and_how_to_answer() -> None:
    text = announcement(NEED, AskPerson(Phase.SPEC_APPROVAL, Reason.GATE, "please read"))
    assert text.startswith("<!-- shelf:work-1 -->")
    assert "Waiting for your approval" in text
    assert "please read" in text
    assert "/shelf approve" in text


def test_only_trusted_people_after_the_last_announcement_decide() -> None:
    comments = [
        comment(1, "/shelf approve"),
        comment(2, "<!-- shelf:work-1 -->\nwaiting"),
        comment(3, "/shelf changes rename it", login="carol"),
        comment(4, "/shelf approve", login="mallory", association="NONE"),
        comment(5, "just chatting"),
        comment(6, "/shelf abort", login="dan", association="COLLABORATOR"),
    ]
    assert events_from(comments) == [
        PersonDecided("carol", DecisionKind.CHANGES, "rename it"),
        PersonDecided("dan", DecisionKind.ABORT),
    ]


async def test_publish_opens_a_draft_pull_request_with_the_requester(settings: GitHubAppSettings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content), path=request.url.path, auth=request.headers["Authorization"])
        return httpx.Response(201, json={"html_url": "https://github.com/acme/shop/pull/12"})

    url = await adapter(settings, httpx.MockTransport(handler)).publish(NEED)
    assert url == "https://github.com/acme/shop/pull/12"
    assert seen["path"] == "/repos/acme/shop/pulls"
    assert seen["auth"] == "Bearer ghs_token"
    assert (seen["head"], seen["base"], seen["draft"]) == ("shelf/work-1", "main", True)
    assert "Requested-by: alice" in str(seen["body"])


async def test_announce_comments_on_the_reviewed_pull_request(settings: GitHubAppSettings) -> None:
    posted: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append((request.url.path, json.loads(request.content)["body"]))
        return httpx.Response(201, json={})

    await adapter(settings, httpx.MockTransport(handler)).announce(
        REVIEW, AskPerson(Phase.PULL_REQUEST, Reason.MERGE, "")
    )
    assert posted[0][0] == "/repos/acme/shop/issues/7/comments"
    assert "Ready for review and merge" in posted[0][1]


async def test_announce_finds_the_pull_request_of_published_work_by_its_branch(settings: GitHubAppSettings) -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        if request.method == "GET":
            return httpx.Response(200, json=[{"number": 12}])
        return httpx.Response(201, json={})

    await adapter(settings, httpx.MockTransport(handler)).announce(
        NEED, AskPerson(Phase.SPEC_APPROVAL, Reason.GATE, "")
    )
    assert "head=acme:shelf/work-1" in paths[0]
    assert paths[1].endswith("/issues/12/comments")


@pytest.mark.parametrize(("merged", "expected"), [(True, True), (False, False)])
async def test_poll_reports_a_closed_pull_request(settings: GitHubAppSettings, *, merged: bool, expected: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": "closed", "merged": merged})

    events = await adapter(settings, httpx.MockTransport(handler)).poll(REVIEW)
    assert events == [PullRequestClosed(merged=expected)]


async def test_poll_reads_decisions_from_the_comments_of_an_open_pull_request(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/pulls/7"):
            return httpx.Response(200, json={"state": "open"})
        return httpx.Response(200, json=[comment(1, "/shelf approve", login="carol")])

    events = await adapter(settings, httpx.MockTransport(handler)).poll(REVIEW)
    assert events == [PersonDecided("carol", DecisionKind.APPROVE)]
