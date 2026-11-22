"""Everything the operator sets through the environment, read once, validated, immutable."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

from shelf.domain.result import Err
from shelf.domain.roles import ROLES, TITLER
from shelf.domain.stepspec import DOCKER_PROFILES, parse_resolvers


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
class ContainerSettings:
    """The runner's address and token, and the shared volumes as the worker sees them."""

    socket: str
    token: str
    steps_dir: Path
    sessions_dir: Path
    """The tools volume is the cache directory: the worker's own set-up and the steps use the same one."""
    model_env: tuple[tuple[str, str], ...] = field(default=(), repr=False)
    """The model credential the worker was given, sent with every step: a container inherits nothing from the worker."""
    docker: bool = False
    """Each step that runs repository code has a Docker daemon of its own, under the runtime the operator named."""


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
    models: tuple[tuple[str, str], ...]
    """The model of each role that has one of its own (``SHELF_MODEL_<ROLE>``), as (role name, model) pairs."""
    max_turns: int
    max_budget_usd: float | None
    nested_sandbox: bool
    sandbox: bool
    isolation: str
    """Where agents run: ``sandbox`` in the worker, or ``container``, one per step through the runner (0019)."""
    container: ContainerSettings | None
    """How the worker reaches the runner and the volumes they share; set exactly when ``isolation`` is ``container``."""
    claude_cli: str | None
    catalog_dir: Path
    cache_dir: str
    allowed_domains: tuple[str, ...]
    web: bool
    nix: bool
    """Whether a repository's Nix flake may give the agent its environment (``SHELF_NIX=on``)."""
    guard_rules_dir: str
    runs_dir: str
    """The folder where the admin page keeps the rules it adds to the guard; empty when this instance has none."""
    """Whether agents may read the web (fetch an address, search); ``SHELF_WEB=off`` turns it off."""
    ci_wait: float
    ci_grace: float
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


ROLE_NAMES = tuple(sorted({role.name for role in ROLES.values()} | {TITLER.name}))
"""The agent roles, by name: what ``SHELF_MODEL_<ROLE>`` may name, in capitals."""


def _models(environ: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """The ``SHELF_MODEL_<ROLE>`` settings. A name that is no role stops the start: a typo would leave a model unset."""
    found: list[tuple[str, str]] = []
    for key, raw in sorted(environ.items()):
        value = raw.strip()
        if not key.startswith("SHELF_MODEL_") or not value:
            continue
        role = key.removeprefix("SHELF_MODEL_").lower()
        if role not in ROLE_NAMES:
            names = ", ".join(f"SHELF_MODEL_{name.upper()}" for name in ROLE_NAMES)
            message = f"{key} names no agent role: the roles are {names}"
            raise MissingSettingError(message)
        found.append((role, value))
    return tuple(found)


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


ISOLATIONS = ("sandbox", "container")


def _isolation(environ: Mapping[str, str]) -> str:
    """``SHELF_ISOLATION``: refused by name when unknown, and when it asks for what does not exist yet."""
    value = environ.get("SHELF_ISOLATION", "").strip().lower() or "sandbox"
    if value not in ISOLATIONS:
        message = f"SHELF_ISOLATION must be one of {', '.join(ISOLATIONS)}, not {value!r}"
        raise ValueError(message)
    return value


CONTAINER_NEEDS = {
    "SHELF_RUNNER_TOKEN": "the token the runner was started with",
    "SHELF_STEPS_DIR": "where the clones volume is mounted in the worker",
    "SHELF_SESSIONS_DIR": "where the sessions volume is mounted in the worker",
    "SHELF_CACHE_DIR": "where the tools volume is mounted in the worker",
}


def _container(environ: Mapping[str, str], isolation: str) -> ContainerSettings | None:
    """What container mode needs, or ``None`` in sandbox mode; a missing setting is named with what it is for."""
    docker = _switch(environ, "SHELF_STEP_DOCKER", default=False)
    if isolation != "container":
        if docker:
            message = (
                "SHELF_STEP_DOCKER=on needs SHELF_ISOLATION=container: a step has its own Docker only in a container"
            )
            raise ValueError(message)
        return None
    if docker and not environ.get("SHELF_STEP_RUNTIME", "").strip():
        message = (
            "SHELF_STEP_DOCKER=on needs SHELF_STEP_RUNTIME (the runtime that makes a Docker daemon in a step safe)"
        )
        raise MissingSettingError(message)
    profile = environ.get("SHELF_STEP_DOCKER_PROFILE", "")
    if docker and profile and profile not in DOCKER_PROFILES:
        message = f"SHELF_STEP_DOCKER_PROFILE must be one of {', '.join(DOCKER_PROFILES)}, not {profile!r}"
        raise ValueError(message)
    if docker and isinstance(resolvers := parse_resolvers(environ.get("SHELF_STEP_DNS", "")), Err):
        raise ValueError(resolvers.error)
    if missing := [name for name in CONTAINER_NEEDS if not environ.get(name, "").strip()]:
        message = "SHELF_ISOLATION=container needs " + ", ".join(
            f"{name} ({CONTAINER_NEEDS[name]})" for name in missing
        )
        raise MissingSettingError(message)
    return ContainerSettings(
        socket=environ.get("SHELF_RUNNER_SOCKET", "").strip() or "/run/shelf-runner/runner.sock",
        token=environ["SHELF_RUNNER_TOKEN"].strip(),
        steps_dir=Path(environ["SHELF_STEPS_DIR"].strip()),
        sessions_dir=Path(environ["SHELF_SESSIONS_DIR"].strip()),
        model_env=tuple((name, environ[name].strip()) for name in MODEL_CREDENTIALS if environ.get(name, "").strip()),
        docker=docker,
    )


def _switch(environ: Mapping[str, str], name: str, *, default: bool) -> bool:
    """An ``on`` or ``off`` variable; anything else is refused by name, not guessed."""
    value = environ.get(name, "").strip().lower()
    if not value:
        return default
    if value not in {"on", "off"}:
        message = f"{name} must be on or off, not {value!r}"
        raise ValueError(message)
    return value == "on"


def from_environ(environ: Mapping[str, str]) -> Settings:
    """Read the settings from ``environ``; raise ``MissingSettingError`` naming what is missing."""
    budget = environ.get("SHELF_MAX_BUDGET_USD", "").strip()
    isolation = _isolation(environ)
    return Settings(
        public_url=_required(environ, "PUBLIC_URL").rstrip("/"),
        session_secret=_required(environ, "SESSION_SECRET"),
        config_path=Path(environ.get("SHELF_CONFIG", "/etc/shelf/shelf.toml")),
        temporal_address=environ.get("TEMPORAL_ADDRESS", "temporal:7233"),
        temporal_namespace=environ.get("TEMPORAL_NAMESPACE", "default"),
        task_queue=environ.get("TASK_QUEUE", "shelf"),
        github=_github(environ),
        model=environ.get("SHELF_MODEL", "").strip() or None,
        models=_models(environ),
        max_turns=int(environ.get("SHELF_MAX_TURNS", "40")),
        max_budget_usd=float(budget) if budget else None,
        nested_sandbox=environ.get("SHELF_NESTED_SANDBOX", "").strip().lower() in {"1", "true", "yes"},
        claude_cli=environ.get("SHELF_CLAUDE_CLI", "").strip() or None,
        catalog_dir=Path(environ.get("SHELF_CATALOG_DIR", "/opt/shelf/catalog")),
        cache_dir=environ.get("SHELF_CACHE_DIR", "").strip(),
        allowed_domains=tuple(
            domain.strip() for domain in environ.get("SHELF_ALLOWED_DOMAINS", "").split(",") if domain.strip()
        ),
        web=_switch(environ, "SHELF_WEB", default=True),
        nix=_switch(environ, "SHELF_NIX", default=False),
        guard_rules_dir=environ.get("SHELF_GUARD_RULES_DIR", "").strip(),
        runs_dir=environ.get("SHELF_RUNS_DIR", "").strip(),
        ci_wait=float(environ.get("SHELF_CI_WAIT", "1800")),
        ci_grace=float(environ.get("SHELF_CI_GRACE", "120")),
        sandbox=environ.get("SHELF_SANDBOX_DISABLED", "").strip().lower() not in {"1", "true", "yes"},
        isolation=isolation,
        container=_container(environ, isolation),
        port=int(environ.get("PORT", "8080")),
        revision=environ.get("SHELF_REVISION", "unknown"),
        model_credential=any(environ.get(key, "").strip() for key in MODEL_CREDENTIALS),
        temporal_ui_upstream=environ.get("TEMPORAL_UI_UPSTREAM", "").strip().rstrip("/"),
        temporal_ui_writable=environ.get("TEMPORAL_UI_WRITABLE", "").strip().lower() in {"1", "true", "yes"},
    )
