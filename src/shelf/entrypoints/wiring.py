"""The composition root: the one place that knows every adapter and joins them to the ports."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from temporalio.client import Client

from shelf.adapters.claude_agent.backend import ClaudeBackend
from shelf.adapters.claude_agent.prompts import load_prompt
from shelf.adapters.config.github import GitHubRepoConfigs
from shelf.adapters.config.toml_files import parse_operator
from shelf.adapters.git.workspace import GitWorkspaces
from shelf.adapters.github_app.app_auth import installation_id, installation_token
from shelf.adapters.github_app.forge import GitHubForge
from shelf.adapters.github_app.pulls import GitHubPullRequests
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.adapters.temporal.runner import TemporalRunner
from shelf.application.steps import Steps
from shelf.domain.model import RepoRef
from shelf.domain.operator import OperatorConfig
from shelf.entrypoints.settings import GitHubApp, Settings

log = logging.getLogger(__name__)


def app_settings(app: GitHubApp) -> GitHubAppSettings:
    """The GitHub adapter's settings from the operator's credentials."""
    return GitHubAppSettings(app.app_id, app.private_key, app.client_id, app.client_secret)


def load_operator(settings: Settings) -> OperatorConfig:
    """Read ``shelf.toml``; without one the instance is open and in local mode, which is logged loudly."""
    if not settings.config_path.exists():
        log.warning("%s not found: this instance is OPEN to anyone with a GitHub account", settings.config_path)
        return OperatorConfig()
    return parse_operator(settings.config_path.read_text(encoding="utf-8"))


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


async def connect(settings: Settings) -> Client:
    """Connect to Temporal."""
    return await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)


def build_services(settings: Settings, github: GitHubApp, client: httpx.AsyncClient, temporal: Client) -> Services:
    """Join every adapter to its port."""
    app = app_settings(github)
    operator = load_operator(settings)
    token_for = token_source(client, app)
    configs = GitHubRepoConfigs(client, app.api_url, token_for)

    async def base_branch(repo: RepoRef) -> str:
        return (await configs.load(repo)).base_branch

    pulls = GitHubPullRequests(client, app, token_for, base_branch)
    steps = Steps(
        workspaces=GitWorkspaces(),
        agents=ClaudeBackend(nested_sandbox=settings.nested_sandbox),
        configs=configs,
        pulls=pulls,
        token_for=token_for,
        prompt_for=load_prompt,
        model=settings.model,
        max_turns=settings.max_turns,
        max_budget_usd=settings.max_budget_usd,
    )
    runner = TemporalRunner(temporal, settings.task_queue, configs, operator.mode)
    return Services(GitHubForge(client, app), configs, pulls, steps, runner, operator)
