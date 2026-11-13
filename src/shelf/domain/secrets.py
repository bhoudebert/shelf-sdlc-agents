"""Which variables of the worker's environment are secrets, and who may see them."""

from collections.abc import Mapping
from typing import Final

WORKER_SECRETS: Final = frozenset({"SESSION_SECRET", "GITHUB_WEBHOOK_SECRET"})
"""Settings of the worker that nothing running in a clone has any use for."""

APP_PREFIX: Final = "GITHUB_APP_"
"""Every GitHub App setting (its id, client secret, private key and where it is kept) starts with this."""

MODEL_CREDENTIALS: Final = frozenset({"CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"})
"""What lets a command spend the operator's model budget. An agent needs it; a repository's own commands do not."""


def is_worker_secret(name: str) -> bool:
    """Whether ``name`` is a setting only the worker itself may use."""
    return name in WORKER_SECRETS or name.startswith(APP_PREFIX)


def hidden_from_agents(environ: Mapping[str, str]) -> dict[str, str]:
    """The worker's secrets, blanked: an agent inherits the worker's environment, and none of this is for it.

    The model credential and ordinary variables (``PATH``, ``HOME``) are left alone, because the agent needs them.
    """
    return {name: "" for name in environ if is_worker_secret(name)}


def for_commands(environ: Mapping[str, str]) -> dict[str, str]:
    """The environment for a repository's own commands: the worker's, without its secrets or the model credential."""
    return {
        name: value for name, value in environ.items() if not is_worker_secret(name) and name not in MODEL_CREDENTIALS
    }
