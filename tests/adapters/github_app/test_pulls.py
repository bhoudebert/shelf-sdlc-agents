import json

import httpx
import pytest

from shelf.adapters.github_app.pulls import GitHubPullRequests, announcement, events_from
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.stage import stage_of
from shelf.domain.work import AskPerson, DecisionKind, PersonDecided, PullRequestClosed, Reason

REPO = RepoRef("acme", "shop")
NEED = WorkContext(WorkId("work-1"), WorkRequest(REPO, "alice", EntryPoint.NEED, "Loyalty points\nmore detail"))
REVIEW = WorkContext(WorkId("work-2"), WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, pull_request=7))


def members_only(login: str, association: str, owner: str) -> bool:
    return association in {"OWNER", "MEMBER"}


def adapter(settings: GitHubAppSettings, handler: httpx.MockTransport) -> GitHubPullRequests:
    async def token_for(repo: RepoRef) -> str:
        return "ghs_token"

    async def base(repo: RepoRef) -> str:
        return "main"

    return GitHubPullRequests(httpx.AsyncClient(transport=handler), settings, token_for, base, members_only)


def comment(identifier: int, body: str, login: str = "bob", association: str = "MEMBER") -> dict[str, object]:
    return {"id": identifier, "body": body, "user": {"login": login}, "author_association": association}


def test_an_announcement_says_what_is_awaited_and_how_to_answer() -> None:
    text = announcement(NEED, AskPerson(Phase.SPEC_APPROVAL, Reason.GATE, "please read"))
    assert text.startswith("<!-- shelf:work-1 -->")
    assert "Waiting for your approval" in text
    assert "please read" in text
    assert "/shelf approve" in text


def not_mallory(login: str, association: str) -> bool:
    return login != "mallory"


def test_only_trusted_people_after_the_last_announcement_decide() -> None:
    comments = [
        comment(1, "/shelf approve"),
        comment(2, "<!-- shelf:work-1 -->\nwaiting"),
        comment(3, "/shelf changes rename it", login="carol"),
        comment(4, "/shelf approve", login="mallory", association="NONE"),
        comment(5, "just chatting"),
        comment(6, "/shelf abort", login="dan", association="COLLABORATOR"),
    ]
    assert events_from(comments, not_mallory) == [
        PersonDecided("carol", DecisionKind.CHANGES, "rename it"),
        PersonDecided("dan", DecisionKind.ABORT),
    ]


def test_nobody_decides_from_a_comment_unless_the_access_list_says_so() -> None:
    assert events_from([comment(1, "/shelf approve")]) == []


async def test_publish_opens_a_draft_pull_request_with_the_requester(settings: GitHubAppSettings) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":  # no pull request exists for this branch yet
            return httpx.Response(200, json=[])
        seen.update(json.loads(request.content), path=request.url.path, auth=request.headers["Authorization"])
        return httpx.Response(201, json={"html_url": "https://github.com/acme/shop/pull/12"})

    url = await adapter(settings, httpx.MockTransport(handler)).publish(NEED, "feat: loyalty points")
    assert url == "https://github.com/acme/shop/pull/12"
    assert seen["path"] == "/repos/acme/shop/pulls"
    assert seen["auth"] == "Bearer ghs_token"
    assert (seen["head"], seen["base"], seen["draft"]) == ("shelf/work-1", "main", True)
    assert "Requested-by: alice" in str(seen["body"])


async def test_publishing_twice_returns_the_pull_request_that_exists(settings: GitHubAppSettings) -> None:
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.url.path)
        if request.url.path.endswith("/pulls/12"):
            return httpx.Response(200, json={"html_url": "https://github.com/acme/shop/pull/12"})
        return httpx.Response(200, json=[{"number": 12}])

    assert (
        await adapter(settings, httpx.MockTransport(handler)).publish(NEED, "feat: loyalty points")
        == "https://github.com/acme/shop/pull/12"
    )
    assert posted == []


async def test_nothing_is_posted_while_there_is_no_pull_request_yet(settings: GitHubAppSettings) -> None:
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            posted.append(request.url.path)
        return httpx.Response(200, json=[])

    pulls = adapter(settings, httpx.MockTransport(handler))
    await pulls.comment(NEED, "hello")
    await pulls.announce(NEED, AskPerson(Phase.SPEC_APPROVAL, Reason.GATE, ""))
    await pulls.set_stage(NEED, stage_of(Phase.INTAKE, None))
    await pulls.set_ready(NEED, ready=True)
    assert posted == []
    assert await pulls.poll(NEED) == []


@pytest.mark.parametrize(
    ("draft", "ready", "mutation"),
    [(True, True, "markPullRequestReadyForReview"), (False, False, "convertPullRequestToDraft")],
)
async def test_the_draft_state_is_changed_through_graphql_when_it_differs(
    settings: GitHubAppSettings, *, draft: bool, ready: bool, mutation: str
) -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/graphql":
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={"data": {}})
        return httpx.Response(200, json={"draft": draft, "node_id": "PR_node"})

    await adapter(settings, httpx.MockTransport(handler)).set_ready(REVIEW, ready=ready)
    assert len(sent) == 1
    assert mutation in str(sent[0]["query"])
    assert sent[0]["variables"] == {"id": "PR_node"}


@pytest.mark.parametrize(("draft", "ready"), [(False, True), (True, False)])
async def test_the_draft_state_is_left_alone_when_it_is_already_right(
    settings: GitHubAppSettings, *, draft: bool, ready: bool
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path != "/graphql"
        return httpx.Response(200, json={"draft": draft, "node_id": "PR_node"})

    await adapter(settings, httpx.MockTransport(handler)).set_ready(REVIEW, ready=ready)


async def test_the_stage_label_replaces_the_previous_one_and_leaves_other_labels(settings: GitHubAppSettings) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[{"name": "bug"}, {"name": "shelf: designing"}])
        return httpx.Response(200, json={})

    await adapter(settings, httpx.MockTransport(handler)).set_stage(REVIEW, stage_of(Phase.IMPLEMENT, None))
    assert ("POST", "/repos/acme/shop/labels") in calls
    assert ("DELETE", "/repos/acme/shop/issues/7/labels/shelf: designing") in calls
    assert ("POST", "/repos/acme/shop/issues/7/labels") in calls
    assert not any(method == "DELETE" and "bug" in path for method, path in calls)


async def test_the_stage_label_that_already_exists_is_not_created_or_added_again(settings: GitHubAppSettings) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=[{"name": "shelf: implementing"}])
        return (
            httpx.Response(422, json={"message": "already exists"})
            if request.url.path.endswith("/labels")
            else httpx.Response(200, json={})
        )

    await adapter(settings, httpx.MockTransport(handler)).set_stage(REVIEW, stage_of(Phase.IMPLEMENT, None))
    assert calls.count(("POST", "/repos/acme/shop/issues/7/labels")) == 0
    assert not any(method == "DELETE" for method, _ in calls)


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


async def test_the_progress_comment_is_created_once_then_edited_in_place(settings: GitHubAppSettings) -> None:
    calls: list[tuple[str, str]] = []
    existing: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json=existing)
        if request.method == "POST":
            existing.append({"id": 55, "body": json.loads(request.content)["body"]})
        return httpx.Response(200, json={})

    pulls = adapter(settings, httpx.MockTransport(handler))
    body = "<!-- shelf-progress:work-2 -->\n### shelf-sdlc: progress"
    await pulls.progress(REVIEW, body)
    await pulls.progress(REVIEW, body + "\nmore")
    assert calls.count(("POST", "/repos/acme/shop/issues/7/comments")) == 1
    assert ("PATCH", "/repos/acme/shop/issues/comments/55") in calls


def test_a_gate_announcement_links_the_document_to_judge() -> None:
    text = announcement(NEED, AskPerson(Phase.SPEC_APPROVAL, Reason.GATE, ""))
    assert (
        "[docs/shelf/work-1/spec.md](https://github.com/acme/shop/blob/shelf/work-1/docs/shelf/work-1/spec.md)" in text
    )
    assert "Read it" not in announcement(NEED, AskPerson(Phase.IMPLEMENT, Reason.FAILURE, "boom"))
