"""The ``PullRequests`` port over GitHub: open the pull request, announce on it, read what people did there."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.commands import HELP, MARKER, is_ours, parse_command
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import EntryPoint
from shelf.domain.work import AskPerson, Event, PersonDecided, PullRequestClosed, Reason

TRUSTED = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
"""Only people with write access count: an outsider's comment is never a decision."""

TokenFor = Callable[[RepoRef], Awaitable[str]]
"""Gives an installation token for a repository. Minted per call, never stored."""

BranchOf = Callable[[WorkContext], str]


def branch_name(work: WorkContext) -> str:
    """The branch a piece of work lives on."""
    return f"shelf/{work.id}"


def title_of(text: str) -> str:
    """A pull request title from the first line of the need."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "shelf work")
    return first[:70]


def announcement(work: WorkContext, ask: AskPerson) -> str:
    """The comment that says what the work waits for and how to answer."""
    heading = {
        Reason.GATE: "Waiting for your approval",
        Reason.ESCALATION: "A person is needed",
        Reason.FAILURE: "A step failed",
        Reason.MERGE: "Ready for review and merge",
    }[ask.reason]
    detail = f"\n\n{ask.detail}" if ask.detail else ""
    return f"{MARKER}{work.id} -->\n**{heading}** ({ask.phase}){detail}\n\n{HELP}"


def events_from(comments: Sequence[Mapping[str, Any]]) -> list[Event]:
    """Decisions found in comments newer than the factory's last announcement, from people who may decide."""
    last = max((int(c["id"]) for c in comments if is_ours(str(c.get("body", "")))), default=0)
    found: list[Event] = []
    for comment in comments:
        if int(comment["id"]) <= last or comment.get("author_association") not in TRUSTED:
            continue
        command = parse_command(str(comment.get("body", "")))
        if command is not None:
            kind, note = command
            found.append(PersonDecided(str(comment["user"]["login"]), kind, note))
    return found


@dataclass(frozen=True, slots=True)
class GitHubPullRequests:
    """Publishes, announces and polls as the GitHub App, with a token per call."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    token_for: TokenFor
    base_branch: Callable[[RepoRef], Awaitable[str]]

    async def publish(self, work: WorkContext) -> str:
        """Open a draft pull request from the work's branch and return its URL."""
        repo = work.request.repo
        body = f"{MARKER}{work.id} -->\n{work.request.text}\n\nRequested-by: {work.request.requester}"
        response = await self._call(
            "POST",
            repo,
            f"/repos/{repo.full_name}/pulls",
            json={
                "title": title_of(work.request.text),
                "head": branch_name(work),
                "base": await self.base_branch(repo),
                "body": body,
                "draft": True,
            },
        )
        return str(response.json()["html_url"])

    async def announce(self, work: WorkContext, ask: AskPerson) -> None:
        """Comment on the pull request with what the work waits for."""
        repo = work.request.repo
        number = await self._number(work)
        await self._call(
            "POST", repo, f"/repos/{repo.full_name}/issues/{number}/comments", json={"body": announcement(work, ask)}
        )

    async def poll(self, work: WorkContext) -> Sequence[Event]:
        """The merge or close of the pull request, and decisions typed in comments since the last announcement."""
        repo = work.request.repo
        number = await self._number(work)
        pull = (await self._call("GET", repo, f"/repos/{repo.full_name}/pulls/{number}")).json()
        if pull["state"] == "closed":
            return [PullRequestClosed(merged=bool(pull.get("merged")))]
        comments = (
            await self._call("GET", repo, f"/repos/{repo.full_name}/issues/{number}/comments?per_page=100")
        ).json()
        return events_from(comments)

    async def _number(self, work: WorkContext) -> int:
        if work.request.entry is EntryPoint.PULL_REQUEST_REVIEW and work.request.pull_request is not None:
            return work.request.pull_request
        repo = work.request.repo
        found = (
            await self._call(
                "GET", repo, f"/repos/{repo.full_name}/pulls?head={repo.owner}:{branch_name(work)}&state=all"
            )
        ).json()
        return int(found[0]["number"])

    async def _call(
        self, method: str, repo: RepoRef, path: str, json: Mapping[str, Any] | None = None
    ) -> httpx.Response:
        token = await self.token_for(repo)
        response = await self.client.request(
            method,
            f"{self.settings.api_url}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json=json,
        )
        response.raise_for_status()
        return response
