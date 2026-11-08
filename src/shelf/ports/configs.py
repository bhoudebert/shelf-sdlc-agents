"""Where a repository's configuration comes from."""

from typing import Protocol

from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef


class RepoConfigs(Protocol):
    """The repository's own file, overridden by an administrator's settings."""

    async def load(self, repo: RepoRef) -> RepoConfig:
        """The effective configuration of ``repo``; defaults when it has none."""
        ...
