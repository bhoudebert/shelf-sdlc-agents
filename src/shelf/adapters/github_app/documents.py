"""The work's documents, read from its branch through GitHub's contents API with an installation token."""

from dataclasses import dataclass

import httpx

from shelf.adapters.github_app.pulls import TokenFor, branch_name
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint
from shelf.domain.roles import DOCUMENT_TITLES, documents_dir

NOT_FOUND = 404


@dataclass(frozen=True, slots=True)
class GitHubDocuments:
    """The ``Documents`` port over GitHub."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    token_for: TokenFor

    async def read(self, repo: RepoRef, work_id: WorkId) -> dict[str, str]:
        """Every document of the work that exists on its branch."""
        token = await self.token_for(repo)
        ref = branch_name(WorkContext(work_id, WorkRequest(repo, "", EntryPoint.NEED)))
        found: dict[str, str] = {}
        for name in DOCUMENT_TITLES:
            response = await self.client.get(
                f"{self.settings.api_url}/repos/{repo.full_name}/contents/{documents_dir(work_id)}/{name}",
                params={"ref": ref},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.raw+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            if response.status_code == NOT_FOUND:
                continue
            response.raise_for_status()
            found[name] = response.text
        return found
