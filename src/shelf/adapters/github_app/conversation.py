"""The conversation of a pull request, read through GitHub's comments API with an installation token."""

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from shelf.adapters.github_app.pulls import COMMENTS_PER_PAGE, MAX_COMMENT_PAGES, TokenFor
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.domain.story import Message, Voice, classify


@dataclass(frozen=True, slots=True)
class GitHubConversations:
    """The ``Conversations`` port over GitHub."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    token_for: TokenFor

    async def description(self, repo: RepoRef, pull_request: int) -> str:
        """The description of the pull request."""
        token = await self.token_for(repo)
        response = await self.client.get(
            f"{self.settings.api_url}/repos/{repo.full_name}/pulls/{pull_request}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response.raise_for_status()
        return str(response.json().get("body") or "")

    async def read(self, repo: RepoRef, pull_request: int) -> Sequence[Message]:
        """Every comment of the pull request, as the story it tells, oldest first."""
        token = await self.token_for(repo)
        story: list[Message] = []
        for page in range(1, MAX_COMMENT_PAGES + 1):
            response = await self.client.get(
                f"{self.settings.api_url}/repos/{repo.full_name}/issues/{pull_request}/comments",
                params={"per_page": COMMENTS_PER_PAGE, "page": page},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            comments = response.json()
            story += [
                message
                for comment in comments
                if (
                    message := classify(
                        str(comment.get("body") or ""),
                        str(comment["user"]["login"]),
                        str(comment.get("created_at") or ""),
                        str(comment.get("html_url") or ""),
                    )
                ).voice
                is not Voice.SUMMARY
            ]
            if len(comments) < COMMENTS_PER_PAGE:
                break
        return story
