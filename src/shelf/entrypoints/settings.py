"""Everything the operator sets through the environment, read once, validated, immutable."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn


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
    sandbox: bool
    port: int
    revision: str
    temporal_ui_upstream: str
    temporal_ui_writable: bool
    model_credential: bool


MODEL_CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL")
"""Any of these gives the agents a model: a Claude token, an API key, or a gateway."""

KEY_FILE = "github-app.pem"
"""The private key's file name inside deploy/secrets, mounted at /run/secrets in the containers."""

WHERE: dict[str, str] = {
    "PUBLIC_URL": "the address people reach this instance at, e.g. https://shelf.example.org",
    "SESSION_SECRET": "any long random string: run `openssl rand -hex 32`",
    "GITHUB_APP_ID": "the number at the top of your GitHub App's settings page (App ID)",
    "GITHUB_APP_SLUG": "the name in your App's public link, github.com/apps/<slug>",
    "GITHUB_APP_CLIENT_ID": "the Client ID at the top of your App's settings page, starting with Iv",
    "GITHUB_APP_CLIENT_SECRET": "generate one under Client secrets on your App's settings page (shown once)",
    "GITHUB_WEBHOOK_SECRET": "the string you typed in the Webhook secret field of the App",
    "GITHUB_APP_PRIVATE_KEY": f"the .pem you downloaded under Private keys: put the file at deploy/secrets/{KEY_FILE}",
}
"""Where each setting comes from, so a missing one says what to do and not only its name."""


def _required(environ: Mapping[str, str], key: str) -> str:
    value = environ.get(key, "").strip()
    if not value:
        hint = f": {WHERE[key]}" if key in WHERE else ""
        message = f"{key} is required{hint}"
        raise MissingSettingError(message)
    return value


def _private_key(environ: Mapping[str, str]) -> str | None:
    inline = environ.get("GITHUB_APP_PRIVATE_KEY", "").strip()
    if inline:
        return inline.replace("\\n", "\n")
    path = Path(environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "").strip() or "/nonexistent")
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _github(environ: Mapping[str, str]) -> GitHubApp | None:
    """The App's credentials, or ``None`` when the App is not registered yet (setup mode)."""
    if not environ.get("GITHUB_APP_ID", "").strip():
        return None
    key = _private_key(environ)
    if key is None:
        message = f"the private key is missing: {WHERE['GITHUB_APP_PRIVATE_KEY']} (or set GITHUB_APP_PRIVATE_KEY)"
        raise MissingSettingError(message)
    return GitHubApp(
        app_id=_required(environ, "GITHUB_APP_ID"),
        private_key=key,
        client_id=_required(environ, "GITHUB_APP_CLIENT_ID"),
        client_secret=_required(environ, "GITHUB_APP_CLIENT_SECRET"),
        slug=_required(environ, "GITHUB_APP_SLUG"),
        webhook_secret=_required(environ, "GITHUB_WEBHOOK_SECRET"),
    )


def exit_with(error: Exception) -> NoReturn:
    """Stop the program with one readable line, as a person who runs it needs, instead of a traceback."""
    message = f"shelf: cannot start: {error}"
    raise SystemExit(message)


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
        sandbox=environ.get("SHELF_SANDBOX_DISABLED", "").strip().lower() not in {"1", "true", "yes"},
        port=int(environ.get("PORT", "8080")),
        revision=environ.get("SHELF_REVISION", "unknown"),
        model_credential=any(environ.get(key, "").strip() for key in MODEL_CREDENTIALS),
        temporal_ui_upstream=environ.get("TEMPORAL_UI_UPSTREAM", "").strip().rstrip("/"),
        temporal_ui_writable=environ.get("TEMPORAL_UI_WRITABLE", "").strip().lower() in {"1", "true", "yes"},
    )
