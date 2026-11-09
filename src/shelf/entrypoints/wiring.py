"""The composition root: the one place that knows every adapter and joins them to the ports."""

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from temporalio.client import Client

from shelf.adapters.caching.conversation import CachedConversations
from shelf.adapters.caching.documents import CachedDocuments
from shelf.adapters.claude_agent.backend import ClaudeBackend
from shelf.adapters.claude_agent.prompts import load_prompt
from shelf.adapters.config.github import GitHubRepoConfigs
from shelf.adapters.config.operator_file import OperatorFile, read_operator
from shelf.adapters.git.workspace import GitWorkspaces
from shelf.adapters.github_app.app_auth import installation_id, installation_token
from shelf.adapters.github_app.context_sources import GitHubContextSources
from shelf.adapters.github_app.conversation import GitHubConversations
from shelf.adapters.github_app.documents import GitHubDocuments
from shelf.adapters.github_app.forge import GitHubForge
from shelf.adapters.github_app.inspector import GitHubAppInspector
from shelf.adapters.github_app.pulls import GitHubPullRequests
from shelf.adapters.github_app.references import GitHubReferences
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.adapters.temporal.runner import TemporalRunner
from shelf.application.steps import Steps
from shelf.domain.access import may_act_from_github
from shelf.domain.model import RepoRef
from shelf.domain.operator import OperatorConfig
from shelf.domain.toolchain import allowed_domains
from shelf.entrypoints.settings import GitHubApp, Settings

log = logging.getLogger(__name__)


def app_settings(app: GitHubApp) -> GitHubAppSettings:
    """The GitHub adapter's settings from the operator's credentials."""
    return GitHubAppSettings(app.app_id, app.private_key, app.client_id, app.client_secret)


def load_operator(settings: Settings) -> OperatorConfig:
    """Read ``shelf.toml``. Without one, or with an empty access list, nobody can sign in, which is logged loudly."""
    return read_operator(settings.config_path)


def token_source(client: httpx.AsyncClient, github: GitHubAppSettings) -> Callable[[RepoRef], Awaitable[str]]:
    """Mint an installation token for a repository on demand. Nothing is cached or stored."""

    async def token_for(repo: RepoRef) -> str:
        now = datetime.now(UTC)
        installation = await installation_id(client, github, repo, now)
        return (await installation_token(client, github, installation, now)).value

    return token_for


@dataclass(frozen=True, slots=True)
class Services:
    """The adapters, built once from the settings."""

    forge: GitHubForge
    configs: GitHubRepoConfigs
    pulls: GitHubPullRequests
    steps: Steps
    runner: TemporalRunner
    operator: OperatorConfig
    """The configuration read at start: the mode."""
    documents: CachedDocuments
    inspector: GitHubAppInspector
    conversations: CachedConversations
    references: GitHubReferences
    context_sources: GitHubContextSources
    current_operator: Callable[[], OperatorConfig]
    """The configuration in force now: the access list follows an edit of the file."""


async def connect(settings: Settings) -> Client:
    """Connect to Temporal."""
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def build_services(settings: Settings, github: GitHubApp, client: httpx.AsyncClient, temporal: Client) -> Services:
    """Join every adapter to its port."""
    app = app_settings(github)
    file = OperatorFile(settings.config_path)
    operator = file.current()
    if not operator.access.is_configured:
        log.warning(
            "The access list is empty: NOBODY can sign in. Edit deploy/config/shelf.toml (users, admins or orgs)."
        )
    token_for = token_source(client, app)
    configs = GitHubRepoConfigs(client, app.api_url, token_for)

    async def base_branch(repo: RepoRef) -> str:
        return (await configs.load(repo)).base_branch

    def may_act(login: str, association: str, owner: str) -> bool:
        return may_act_from_github(file.current().access, login, association, owner)

    pulls = GitHubPullRequests(client, app, token_for, base_branch, may_act)
    context_cache = Path(settings.cache_dir) / "context" if settings.cache_dir else None
    context_sources = GitHubContextSources(client, app, context_cache)
    steps = Steps(
        workspaces=GitWorkspaces(),
        agents=ClaudeBackend(
            nested_sandbox=settings.nested_sandbox,
            sandbox=settings.sandbox,
            cli_path=settings.claude_cli,
            allowed_domains=allowed_domains(settings.allowed_domains),
        ),
        configs=configs,
        pulls=pulls,
        token_for=token_for,
        prompt_for=load_prompt,
        model=settings.model,
        max_turns=settings.max_turns,
        max_budget_usd=settings.max_budget_usd,
        cache_dir=settings.cache_dir,
        base_path=os.environ.get("PATH", ""),
        ci_wait=settings.ci_wait,
        ci_grace=settings.ci_grace,
        context_sources=context_sources,
    )
    runner = TemporalRunner(temporal, settings.task_queue, configs, operator.mode, app.web_url)
    documents = CachedDocuments(GitHubDocuments(client, app, token_for))
    return Services(
        GitHubForge(client, app),
        configs,
        pulls,
        steps,
        runner,
        operator,
        documents,
        GitHubAppInspector(client, app),
        CachedConversations(GitHubConversations(client, app, token_for)),
        GitHubReferences(client, app, token_for),
        context_sources,
        file.current,
    )
