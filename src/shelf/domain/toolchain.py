"""The environment an agent works in: where its tools and caches live, and which sites its commands may reach. Pure."""

import re
import shlex
from collections.abc import Mapping
from pathlib import PurePosixPath

from shelf.domain.mise_config import NO_CODE_AT_INSTALL
from shelf.domain.model import RepoRef

MISE_VERSION_HINT = "mise.toml, .mise.toml or .tool-versions"
"""Where a repository says which tools (a JDK, Maven, Node, Python...) it needs."""

DEFAULT_ALLOWED_DOMAINS: tuple[str, ...] = (
    "github.com",
    "api.github.com",
    "*.githubusercontent.com",
    "mise.jdx.dev",
    "mise-versions.jdx.dev",
    "mise-java.jdx.dev",
    "api.adoptium.net",
    "cdn.azul.com",
    "corretto.aws",
    "download.java.net",
    "download.oracle.com",
    "archive.apache.org",
    "dlcdn.apache.org",
    "repo.maven.apache.org",
    "repo1.maven.org",
    "services.gradle.org",
    "plugins.gradle.org",
    "registry.npmjs.org",
    "nodejs.org",
    "pypi.org",
    "files.pythonhosted.org",
    "static.crates.io",
    "index.crates.io",
    "crates.io",
    "proxy.golang.org",
    "sum.golang.org",
)
"""What a build normally needs to fetch: the tool downloads, the common package registries, GitHub."""

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")


def repository_folder(full_name: str) -> str:
    """The folder, inside the cache, of one repository's home: ``home/<owner>__<name>``."""
    owner, _, name = full_name.partition("/")
    return f"home/{_UNSAFE.sub('_', f'{owner}__{name}')}"


def repository_home(cache_dir: str, repo: RepoRef) -> str:
    """The home directory of the agents working on ``repo``: its tools and package caches live there and nowhere shared.

    Each repository has its own, so a tampered download in one can never be picked up by the work of another.
    """
    return str(PurePosixPath(cache_dir) / repository_folder(repo.full_name))


def toolchain_env(cache_dir: str, repo: RepoRef, workdir: str, path: str) -> dict[str, str]:
    """The variables that give an agent the repository's own tools: nothing when no cache directory is configured.

    ``mise`` reads the repository's declaration and installs what it names into the repository's home; its shims then
    put those tools on the ``PATH`` of every command, so ``java``, ``mvn`` or ``node`` just work after ``mise install``.
    """
    if not cache_dir:
        return {}
    home = repository_home(cache_dir, repo)
    return {
        "HOME": home,
        "MISE_YES": "1",
        "MISE_LOCKFILE": "false",
        "MISE_DISABLE_BACKENDS": NO_CODE_AT_INSTALL,
        "MISE_TRUSTED_CONFIG_PATHS": workdir,
        "PATH": f"{home}/.local/share/mise/shims:{path}",
    }


def allowed_domains(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The sites a sandboxed command may reach: the defaults and the operator's own, without repeats."""
    return tuple(dict.fromkeys((*DEFAULT_ALLOWED_DOMAINS, *extra)))


SANDBOX_RECIPES = (
    "The repository's checks (`checks` in its configuration) are run by the system after you finish, outside this "
    "sandbox, with the tools that `mise` or the flake declares and with the network: declare what the project needs in "
    "`mise.toml` and do not spend your turns making a build run here. A command in this sandbox may write only the "
    "clone and `$TMPDIR`. The checks are read from the repository's default branch, not from yours: "
    "`.shelf/config.toml` is not yours to edit, and a change to it is discarded."
)

DOCKER_OFF_NOTE = (
    "Docker is not available and must not be tried: a compose file is for people, so tests have to run without it (an "
    "embedded database, or a test that is skipped when the service is missing, and say so)."
)
DOCKER_ON_NOTE = (
    "Docker: this step has its own Docker daemon, running in its own virtual machine and gone when the step ends, so "
    "start what the tests need: `docker compose up -d --wait`, a Testcontainers test or `docker run`, for a database, "
    "a cache, an identity server or a service built from the repository's Dockerfile. It is not the host's Docker: "
    "what you start lives and ends with this step, so stop nothing you did not start, and expect the first image pull "
    "to take a while."
)

TOOLCHAIN_NOTE = (
    "Tools: this environment has no JDK, Node, Maven or similar until you ask for them. If the repository declares its "
    f"tools ({MISE_VERSION_HINT}), run `mise install` first: it installs them into this sandbox, where your commands "
    "can use them. Then do what a developer does: run the repository's own build and tests (see its README, CLAUDE.md "
    "or AGENTS.md) yourself, and fix what fails, before you finish. If the repository declares no tools, do not stop "
    "there: the checks its CI runs are the ones that matter. Read its workflows (`.github/workflows/`), find the job "
    "that runs the linter, the type check and the tests, and the tool versions it sets up (setup-node's "
    "`node-version`, `.nvmrc`, `engines` in `package.json`, `.python-version`, `go.mod`, `rust-toolchain`...). Run the "
    "same commands with those versions through `mise exec <tool>@<version> -- <command>` (for example "
    "`mise exec node@24 -- npm run quality`): it installs the version into this sandbox and writes nothing into the "
    "repository, so never `mise use`. "
    "If a check still cannot run here, say which command and why in your answer instead of claiming a result you could "
    "not check. " + SANDBOX_RECIPES
)


def setup_command(env: Mapping[str, str], tools: Mapping[str, str]) -> str:
    """The shell command that installs ``tools`` (tool to version) into the home ``env`` names, as its default.

    ``mise use --global`` writes the versions into that home's own configuration, never into the repository, and
    installs them. Every word is quoted, although the versions were already checked to be plain.
    """
    home = env["HOME"]
    assignments = " ".join(f"{name}={shlex.quote(value)}" for name, value in env.items())
    versions = " ".join(shlex.quote(f"{tool}@{version}") for tool, version in tools.items())
    return f"mkdir -p {shlex.quote(home)} && env {assignments} mise use --global --yes {versions}"


def dependencies_command(env: Mapping[str, str]) -> str:
    """The shell command that installs a Node repository's locked dependencies, without running any of their scripts."""
    assignments = " ".join(f"{name}={shlex.quote(value)}" for name, value in env.items())
    return f"env {assignments} npm ci --ignore-scripts --no-audit --no-fund"


def dependencies_ready() -> str:
    """What the agent is told once the worker has installed the locked dependencies."""
    return (
        "Dependencies: the worker ran `npm ci --ignore-scripts`, so `node_modules` is there with the repository's own "
        "linters, formatters and test runners: run them with `npx --no-install` or `npm run`, never download them. "
        "Install scripts did not run."
    )


def dependencies_failed(reason: str) -> str:
    """What the agent is told when the locked dependencies could not be installed."""
    return (
        f"Dependencies: the worker tried `npm ci --ignore-scripts` and it failed: {reason}. `node_modules` is missing."
    )


def with_environment(env: Mapping[str, str], command: str) -> str:
    """``command`` run with ``env`` set, for a check of the repository's own; ``sh -c`` keeps a compound one whole."""
    if not env:
        return command
    assignments = " ".join(f"{name}={shlex.quote(value)}" for name, value in env.items())
    return f"env {assignments} sh -c {shlex.quote(command)}"


def declared_ready(tools: Mapping[str, str], ignored: tuple[str, ...] = ()) -> str:
    """What the agent is told once the worker has installed what the repository's declaration names."""
    names = ", ".join(f"{tool} {version}" for tool, version in tools.items())
    left = f" Left out, because installing it would run code in the worker: {'; '.join(ignored)}." if ignored else ""
    return (
        f"Tools: the worker has installed what the repository declares for mise ({names}) into your home, and they are "
        "on your path. Do not install them again. Do what a developer does: run the repository's own build and tests "
        "(see its README, CLAUDE.md or AGENTS.md) and fix what fails before you finish. If a check still cannot run "
        f"here, say which command and why instead of claiming a result.{left} " + SANDBOX_RECIPES
    )


def nothing_to_install(ignored: tuple[str, ...]) -> str:
    """What the agent is told when the declaration names nothing the worker may install."""
    why = f" Left out: {'; '.join(ignored)}." if ignored else ""
    return f"Tools: the repository's mise declaration names nothing the worker installs.{why} {TOOLCHAIN_NOTE}"


def declared_failed(reason: str) -> str:
    """What the agent is told when the worker could not install what the repository declares for mise."""
    return f"Tools: `mise install` by the worker for what the repository declares failed: {reason}. {TOOLCHAIN_NOTE}"


def tools_ready(tools: Mapping[str, str]) -> str:
    """What the agent is told once the worker has installed what the repository's CI uses."""
    names = ", ".join(f"{tool} {version}" for tool, version in tools.items())
    return (
        f"Tools: the worker has installed what the repository's CI uses ({names}) into your home, and they are on your "
        "path. Do not install them again. Do what a developer does: run the checks the repository's CI runs, as CI "
        "runs them (find them in `.github/workflows/`, and see its README, CLAUDE.md or AGENTS.md), and fix what fails "
        "before you finish. If a check still cannot run here, say which command and why instead of claiming a result."
    )


def tools_failed(tools: Mapping[str, str], reason: str) -> str:
    """What the agent is told when the worker could not install what the repository's CI uses."""
    names = ", ".join(f"{tool} {version}" for tool, version in tools.items())
    return (
        f"Tools: the worker tried to install what the repository's CI uses ({names}) and could not: {reason}. "
        f"{TOOLCHAIN_NOTE}"
    )
