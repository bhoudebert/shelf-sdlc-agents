"""Using a repository's Nix flake for the environment of the agent. Pure: the commands, and what to make of them."""

import json
import re
import shlex
from collections.abc import Mapping
from typing import cast

NIX_BIN = "/nix/var/nix/profiles/default/bin"
"""Where the Nix client is, in the store the daemon's image fills."""

CERTIFICATES = "/nix/var/nix/profiles/default/etc/ssl/certs/ca-bundle.crt"
FLAKE = "flake.nix"
TIME_LIMIT = 600
"""Seconds the evaluation of a flake may take."""

_NIX_IN_CI = re.compile(
    r"install-nix-action|nix-installer-action|\bnix\s+(?:develop|build|run|shell|flake|fmt)\b|nixbuild", re.IGNORECASE
)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DENIED = frozenset(
    {
        "HOME", "USER", "LOGNAME", "SHELL", "PWD", "OLDPWD", "TMPDIR", "TMP", "TEMP", "TEMPDIR", "TERM", "IFS",
        "BASH_ENV", "ENV", "PROMPT_COMMAND", "PS1", "SHLVL", "SSL_CERT_FILE", "CURL_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
        "GIT_SSL_CAINFO",
    }
)  # fmt: skip
_DENIED_PREFIXES = ("NIX_", "LD_", "DYLD_", "ANTHROPIC", "CLAUDE", "GH_", "GITHUB", "WARDEN", "SHELF_", "BASH_FUNC_")
MAX_VALUE = 4096


def has_flake(files: Mapping[str, str]) -> bool:
    """Whether the repository has a flake."""
    return FLAKE in files


def ci_uses_nix(files: Mapping[str, str]) -> bool:
    """Whether a workflow of the repository runs through Nix: then the flake is what CI builds with."""
    return any(name.startswith(".github/workflows/") and _NIX_IN_CI.search(text) for name, text in files.items())


def print_dev_env_command(home: str) -> str:
    """The shell command that asks Nix for the environment of the flake's development shell, and nothing else.

    It runs in a scrubbed environment (nothing of the worker's, no token), asks the daemon to build, writes no lock
    file into the repository and does not enter the shell, so that its hook never runs. Nix's own messages go to a file
    in the home and come back only when it fails.
    """
    log = f"{home}/.nix-last-error"
    nix = " ".join(
        (
            "env -i",
            f"HOME={shlex.quote(home)}",
            f"PATH={NIX_BIN}",
            "NIX_REMOTE=daemon",
            f"NIX_SSL_CERT_FILE={CERTIFICATES}",
            "NIX_CONFIG='experimental-features = nix-command flakes'",
            f"timeout {TIME_LIMIT}",
            "nix print-dev-env --json --no-write-lock-file",
        )
    )
    return (
        f"mkdir -p {shlex.quote(home)} && out=$({nix} 2>{shlex.quote(log)}) "
        f"|| {{ tail -n 3 {shlex.quote(log)} >&2; exit 1; }}; printf '%s' \"$out\""
    )


def _plain(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > MAX_VALUE or "\n" in value or "\0" in value:
        return None
    return value


def dev_environment(text: str) -> tuple[str, dict[str, str]]:
    """The ``PATH`` and the safe exported variables of the development shell Nix printed.

    The path must be absolute folders only. A variable is passed only when it is exported, plain text, and neither a
    home, a shell, a certificate, a credential of ours nor a variable that makes a program load code; the rest of what
    a shell sets is not the agent's business.
    """
    try:
        document: object = json.loads(text)
    except ValueError:
        return "", {}
    variables = cast("dict[str, object]", document).get("variables") if isinstance(document, dict) else None
    if not isinstance(variables, dict):
        return "", {}
    found: dict[str, str] = {}
    path = ""
    for name, entry in cast("dict[str, object]", variables).items():
        if not isinstance(entry, dict) or cast("dict[str, object]", entry).get("type") != "exported":
            continue
        value = _plain(cast("dict[str, object]", entry).get("value"))
        if value is None:
            continue
        if name == "PATH":
            folders = value.split(":")
            path = value if all(folder.startswith("/") for folder in folders) else ""
        elif _NAME.fullmatch(name) and name not in _DENIED and not name.startswith(_DENIED_PREFIXES):
            found[name] = value
    return path, found


def nix_ready(count: int) -> str:
    """What the agent is told once the flake's environment is on its path."""
    return (
        "Tools: the worker has made the repository's Nix development shell available: its tools are on your path"
        f"{f' with {count} of its variables' if count else ''}. Do not install them again. Do what a developer does: "
        "run "
        "the checks the repository's CI runs, as CI runs them (find them in `.github/workflows/`, and see its README, "
        "CLAUDE.md or AGENTS.md), and fix what fails before you finish. If a check still cannot run here, say which "
        "command and why instead of claiming a result. Its tools are in /nix/store, which you may read but not write."
    )


def nix_failed(reason: str) -> str:
    """What the agent is told when the flake's environment could not be made available."""
    return f"Tools: the worker tried to use the repository's Nix development shell and could not: {reason}."
