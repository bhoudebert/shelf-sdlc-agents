"""The environment an agent works in: where its tools and caches live, and which sites its commands may reach. Pure."""

import re
from pathlib import PurePosixPath

from shelf.domain.model import RepoRef

MISE_VERSION_HINT = "mise.toml, .mise.toml or .tool-versions"
"""Where a repository says which tools (a JDK, Maven, Node, Python...) it needs."""

DEFAULT_ALLOWED_DOMAINS: tuple[str, ...] = (
    "github.com",
    "api.github.com",
    "*.githubusercontent.com",
    "mise.jdx.dev",
    "mise-versions.jdx.dev",
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


def repository_home(cache_dir: str, repo: RepoRef) -> str:
    """The home directory of the agents working on ``repo``: its tools and package caches live there and nowhere shared.

    Each repository has its own, so a tampered download in one can never be picked up by the work of another.
    """
    name = _UNSAFE.sub("_", f"{repo.owner}__{repo.name}")
    return str(PurePosixPath(cache_dir) / "home" / name)


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
        "MISE_TRUSTED_CONFIG_PATHS": workdir,
        "PATH": f"{home}/.local/share/mise/shims:{path}",
    }


def allowed_domains(extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The sites a sandboxed command may reach: the defaults and the operator's own, without repeats."""
    return tuple(dict.fromkeys((*DEFAULT_ALLOWED_DOMAINS, *extra)))


TOOLCHAIN_NOTE = (
    "Tools: this environment has no JDK, Node, Maven or similar until you ask for them. If the repository declares its "
    f"tools ({MISE_VERSION_HINT}), run `mise install` first: it installs them into this sandbox, where your commands "
    "can use them. Then do what a developer does: run the repository's own build and tests (see its README, CLAUDE.md "
    "or AGENTS.md) yourself, and fix what fails, before you finish. If a tool you need is not declared, say so in your "
    "answer instead of claiming a result you could not check."
)
