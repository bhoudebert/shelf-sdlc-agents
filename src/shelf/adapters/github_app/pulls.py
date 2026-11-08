"""The ``PullRequests`` port over GitHub: open the pull request, announce on it, read what people did there."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.commands import HELP, MARKER, is_ours, parse_command
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.progress import marker
from shelf.domain.roles import documents_dir
from shelf.domain.stage import PREFIX, Stage
from shelf.domain.work import AskPerson, Event, PersonDecided, PullRequestClosed, Reason

COMMENTS_PER_PAGE = 100
MAX_COMMENT_PAGES = 5

TRUSTED = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
"""Only people with write access count: an outsider's comment is never a decision."""

TokenFor = Callable[[RepoRef], Awaitable[str]]
"""Gives an installation token for a repository. Minted per call, never stored."""

BranchOf = Callable[[WorkContext], str]


def branch_name(work: WorkContext) -> str:
    """The branch a piece of work lives on."""
    return f"shelf/{work.id}"


def announcement(work: WorkContext, ask: AskPerson) -> str:
    """The comment that says what the work waits for and how to answer."""
    heading = {
        Reason.GATE: "Waiting for your approval",
        Reason.ESCALATION: "A person is needed",
        Reason.FAILURE: "A step failed",
        Reason.MERGE: "Ready for review and merge",
    }[ask.reason]
    detail = f"\n\n{ask.detail}" if ask.detail else ""
    read = _where_to_read(work, ask.phase)
    return f"{MARKER}{work.id} -->\n**{heading}** ({ask.phase}){detail}{read}\n\n{HELP}"


READ_AT: dict[Phase, str] = {
    Phase.SPEC_APPROVAL: "spec.md",
    Phase.DESIGN_REVIEW: "design.md",
    Phase.PULL_REQUEST: "plan.md",
}


def _where_to_read(work: WorkContext, phase: Phase) -> str:
    """A link to the document the person is asked to judge, when there is one."""
    name = READ_AT.get(phase)
    if name is None:
        return ""
    path = f"{documents_dir(work.id)}/{name}"
    return f"\n\nRead it: [{path}](https://github.com/{work.request.repo.full_name}/blob/{branch_name(work)}/{path})"


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

    async def publish(self, work: WorkContext, title: str) -> str:
        """Open a draft pull request titled ``title`` from the work's branch, or retitle the one that exists."""
        repo = work.request.repo
        existing = await self._number(work)
        if existing is not None:
            return await self._retitle(work, existing, title)
        body = f"{MARKER}{work.id} -->\n{work.request.text}\n\nRequested-by: {work.request.requester}"
        response = await self._call(
            "POST",
            repo,
            f"/repos/{repo.full_name}/pulls",
            json={
                "title": title,
                "head": branch_name(work),
                "base": await self.base_branch(repo),
                "body": body,
                "draft": True,
            },
        )
        return str(response.json()["html_url"])

    async def announce(self, work: WorkContext, ask: AskPerson) -> None:
        """Comment on the pull request with what the work waits for."""
        await self.comment(work, announcement(work, ask))

    async def progress(self, work: WorkContext, body: str) -> None:
        """Keep one progress comment, found by its hidden marker and edited in place after every step."""
        repo = work.request.repo
        number = await self._number(work)
        if number is None:
            return
        base = f"/repos/{repo.full_name}/issues"
        found = await self._find_comment(repo, number, marker(work.id))
        if found is None:
            await self._call("POST", repo, f"{base}/{number}/comments", json={"body": body})
        else:
            await self._call("PATCH", repo, f"{base}/comments/{found}", json={"body": body})

    async def _find_comment(self, repo: RepoRef, number: int, needle: str) -> int | None:
        """The id of our comment holding ``needle``, looking through up to five pages of the conversation."""
        for page in range(1, MAX_COMMENT_PAGES + 1):
            path = f"/repos/{repo.full_name}/issues/{number}/comments?per_page=100&page={page}"
            comments = (await self._call("GET", repo, path)).json()
            for comment in comments:
                if needle in str(comment.get("body", "")):
                    return int(comment["id"])
            if len(comments) < COMMENTS_PER_PAGE:
                return None
        return None

    async def set_ready(self, work: WorkContext, *, ready: bool) -> None:
        """Mark the pull request ready for review, or back to draft. GitHub offers this only through GraphQL."""
        repo = work.request.repo
        number = await self._number(work)
        if number is None:
            return
        pull = (await self._call("GET", repo, f"/repos/{repo.full_name}/pulls/{number}")).json()
        if bool(pull.get("draft")) != ready:  # already in the wanted state
            return
        mutation = "markPullRequestReadyForReview" if ready else "convertPullRequestToDraft"
        query = f"mutation($id: ID!) {{ {mutation}(input: {{pullRequestId: $id}}) {{ pullRequest {{ id }} }} }}"
        await self._call("POST", repo, "/graphql", json={"query": query, "variables": {"id": pull["node_id"]}})

    async def set_stage(self, work: WorkContext, stage: Stage) -> None:
        """Keep exactly one ``shelf:`` label on the pull request: ``stage``."""
        repo = work.request.repo
        number = await self._number(work)
        if number is None:
            return
        base = f"/repos/{repo.full_name}"
        await self._call(
            "POST", repo, f"{base}/labels", json={"name": stage.name, "color": stage.color}, tolerate=(422,)
        )
        current = (await self._call("GET", repo, f"{base}/issues/{number}/labels?per_page=100")).json()
        names = {str(label["name"]) for label in current}
        for stale in sorted(name for name in names if name.startswith(PREFIX) and name != stage.name):
            await self._call("DELETE", repo, f"{base}/issues/{number}/labels/{quote(stale, safe='')}", tolerate=(404,))
        if stage.name not in names:
            await self._call("POST", repo, f"{base}/issues/{number}/labels", json={"labels": [stage.name]})

    async def comment(self, work: WorkContext, body: str) -> None:
        """Post ``body`` as a comment on the pull request."""
        repo = work.request.repo
        number = await self._number(work)
        if number is None:  # the pull request is not open yet: the first step's result is in the commit
            return
        await self._call("POST", repo, f"/repos/{repo.full_name}/issues/{number}/comments", json={"body": body})

    async def poll(self, work: WorkContext) -> Sequence[Event]:
        """The merge or close of the pull request, and decisions typed in comments since the last announcement."""
        repo = work.request.repo
        number = await self._number(work)
        if number is None:
            return []
        pull = (await self._call("GET", repo, f"/repos/{repo.full_name}/pulls/{number}")).json()
        if pull["state"] == "closed":
            return [PullRequestClosed(merged=bool(pull.get("merged")))]
        comments = (
            await self._call("GET", repo, f"/repos/{repo.full_name}/issues/{number}/comments?per_page=100")
        ).json()
        return events_from(comments)

    async def _retitle(self, work: WorkContext, number: int, title: str) -> str:
        """The URL of the pull request, after giving it ``title`` if it carries another."""
        repo = work.request.repo
        path = f"/repos/{repo.full_name}/pulls/{number}"
        pull = (await self._call("GET", repo, path)).json()
        if pull.get("title") != title:
            await self._call("PATCH", repo, path, json={"title": title})
        return str(pull["html_url"])

    async def _number(self, work: WorkContext) -> int | None:
        """The pull request of this work, or ``None`` while there is none."""
        if work.request.entry is EntryPoint.PULL_REQUEST_REVIEW and work.request.pull_request is not None:
            return work.request.pull_request
        repo = work.request.repo
        found = (
            await self._call(
                "GET", repo, f"/repos/{repo.full_name}/pulls?head={repo.owner}:{branch_name(work)}&state=all"
            )
        ).json()
        return int(found[0]["number"]) if found else None

    async def _call(
        self,
        method: str,
        repo: RepoRef,
        path: str,
        json: Mapping[str, Any] | None = None,
        tolerate: tuple[int, ...] = (),
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
        if response.status_code not in tolerate:
            response.raise_for_status()
        return response
