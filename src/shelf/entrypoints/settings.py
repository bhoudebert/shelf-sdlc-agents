"""Everything the operator sets through the environment, read once, validated, immutable."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class MissingSettingError(ValueError):
    """A required setting is absent."""


@dataclass(frozen=True, slots=True)
class GitHubApp:
    """The registered GitHub App's credentials."""

    app_id: str
    private_key: str
    client_id: str
    client_secret: str
    slug: str
    webhook_secret: str


@dataclass(frozen=True, slots=True)
class Settings:
    """The instance's settings."""

    public_url: str
    session_secret: str
    config_path: Path
    temporal_address: str
    temporal_namespace: str
    task_queue: str
    github: GitHubApp | None
    model: str | None
    max_turns: int
    max_budget_usd: float | None
    nested_sandbox: bool
    port: int
    revision: str


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        message = f"{key} is required"
        raise MissingSettingError(message)
    return value


def _private_key(environ: Mapping[str, str]) -> str | None:
    inline = environ.get("GITHUB_APP_PRIVATE_KEY", "").strip()
    if inline:
        return inline.replace("\\n", "\n")
    path = environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
    return Path(path).read_text(encoding="utf-8") if path else None


def _github(environ: Mapping[str, str]) -> GitHubApp | None:
    """The App's credentials, or ``None`` when the App is not registered yet (setup mode)."""
    if not environ.get("GITHUB_APP_ID", "").strip():
        return None
    key = _private_key(environ)
    if key is None:
        message = "GITHUB_APP_PRIVATE_KEY or GITHUB_APP_PRIVATE_KEY_PATH is required with GITHUB_APP_ID"
        raise MissingSettingError(message)
    return GitHubApp(
        app_id=_required(environ, "GITHUB_APP_ID"),
        private_key=key,
        client_id=_required(environ, "GITHUB_APP_CLIENT_ID"),
        client_secret=_required(environ, "GITHUB_APP_CLIENT_SECRET"),
        slug=_required(environ, "GITHUB_APP_SLUG"),
        webhook_secret=_required(environ, "GITHUB_WEBHOOK_SECRET"),
    )


def from_environ(environ: Mapping[str, str]) -> Settings:
    """Read the settings from ``environ``; raise ``MissingSettingError`` naming what is missing."""
    budget = environ.get("SHELF_MAX_BUDGET_USD", "").strip()
    return Settings(
        public_url=_required(environ, "PUBLIC_URL").rstrip("/"),
        session_secret=_required(environ, "SESSION_SECRET"),
        config_path=Path(environ.get("SHELF_CONFIG", "/etc/shelf/shelf.toml")),
        temporal_address=environ.get("TEMPORAL_ADDRESS", "temporal:7233"),
        temporal_namespace=environ.get("TEMPORAL_NAMESPACE", "default"),
        task_queue=environ.get("TASK_QUEUE", "shelf"),
        github=_github(environ),
        model=environ.get("SHELF_MODEL", "").strip() or None,
        max_turns=int(environ.get("SHELF_MAX_TURNS", "40")),
        max_budget_usd=float(budget) if budget else None,
        nested_sandbox=environ.get("SHELF_NESTED_SANDBOX", "").strip().lower() in {"1", "true", "yes"},
        port=int(environ.get("PORT", "8080")),
        revision=environ.get("SHELF_REVISION", "unknown"),
    )
