"""A repository's ``.shelf/config.toml``, read from GitHub with the App's token."""

from dataclasses import dataclass

import httpx

from shelf.adapters.config.toml_files import parse_repo_config
from shelf.adapters.github_app.pulls import TokenFor
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef

CONFIG_PATH = ".shelf/config.toml"
NOT_FOUND = 404


@dataclass(frozen=True, slots=True)
class GitHubRepoConfigs:
    """The ``RepoConfigs`` port: the repository's own file, or the defaults when it has none."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    token_for: TokenFor

    async def load(self, repo: RepoRef) -> RepoConfig:
        """The configuration of ``repo``. An invalid file raises ``InvalidConfigError``, never silent defaults."""
        response = await self.client.get(
            f"{self.settings.api_url}/repos/{repo.full_name}/contents/{CONFIG_PATH}",
            headers={
                "Authorization": f"Bearer {await self.token_for(repo)}",
                "Accept": "application/vnd.github.raw+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if response.status_code == NOT_FOUND:
            return RepoConfig()
        response.raise_for_status()
        return parse_repo_config(response.text)
