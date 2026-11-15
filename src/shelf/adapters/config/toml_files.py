"""Parsing the two configuration files. Pure functions from text to domain values; unknown keys are refused."""

import tomllib
from collections.abc import Mapping
from typing import Any

from shelf.domain.access import AccessRules
from shelf.domain.config import InvalidConfigError, RepoConfig, Role
from shelf.domain.operator import OperatorConfig
from shelf.domain.pipeline import EntryPoint
from shelf.domain.policy import Policy
from shelf.domain.polling import Mode
from shelf.domain.results import KINDS, Conflicts, Results
from shelf.domain.roles import ROLES, TITLER

ConfigError = InvalidConfigError
"""The name this module's callers know."""


def _only(section: str, table: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(table) - allowed
    if unknown:
        message = f"[{section}] has unknown keys: {', '.join(sorted(unknown))}"
        raise ConfigError(message)


def _names(table: Mapping[str, Any], key: str) -> frozenset[str]:
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):  # pyright: ignore[reportUnknownVariableType]
        message = f"{key} must be a list of strings"
        raise ConfigError(message)
    return frozenset(value)  # pyright: ignore[reportUnknownArgumentType]


def _load(text: str) -> dict[str, Any]:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        message = f"not valid TOML: {error}"
        raise ConfigError(message) from error


def _bindings(roles: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    """``[roles.<name>] use = [...]``: the catalog sources each existing agent role loads."""
    known = sorted({role.name for role in ROLES.values()} | {TITLER.name})
    bound: dict[str, tuple[str, ...]] = {}
    for name, table in roles.items():
        if name not in known:
            message = f"[roles.{name}] is not an agent role; the roles are {', '.join(known)}"
            raise ConfigError(message)
        if not isinstance(table, dict):
            message = f"[roles.{name}] must be a table with a use list"
            raise ConfigError(message)
        _only(f"roles.{name}", table, {"use"})  # pyright: ignore[reportUnknownArgumentType]
        bound[name] = tuple(sorted(_names(table, "use")))  # pyright: ignore[reportUnknownArgumentType]
    return bound


def parse_operator(text: str) -> OperatorConfig:
    """Read ``shelf.toml``: ``mode``, the ``[access]`` section and the ``[roles.<name>]`` bindings."""
    document = _load(text)
    _only("shelf", document, {"mode", "access", "roles"})
    access = document.get("access", {})
    _only("access", access, {"orgs", "users", "admins"})
    try:
        mode = Mode(document.get("mode", "local"))
    except ValueError as error:
        message = f"mode must be one of {', '.join(m.value for m in Mode)}"
        raise ConfigError(message) from error
    return OperatorConfig(
        AccessRules(_names(access, "orgs"), _names(access, "users"), _names(access, "admins")),
        mode,
        _bindings(document.get("roles", {})),
    )


def _results(table: Mapping[str, Any]) -> Results:
    """``[results]``: where the specs and the decision records of a repository are, and which of them a run writes."""
    _only("results", table, {"specs", "decisions", "write", "conflicts"})
    defaults = Results()
    folders: dict[str, str] = {}
    for key, default in (("specs", defaults.specs), ("decisions", defaults.decisions)):
        value = table.get(key, default)
        if not isinstance(value, str) or not value.strip() or value.startswith(("/", "..")) or ".." in value.split("/"):
            message = f"[results] {key} must be a folder inside the repository, such as {default!r}"
            raise ConfigError(message)
        folders[key] = value.strip("/")
    write = _names(table, "write") if "write" in table else defaults.write
    if not write <= KINDS:
        message = f"[results] write may list {', '.join(sorted(KINDS))}, not {', '.join(sorted(write - KINDS))}"
        raise ConfigError(message)
    try:
        conflicts = Conflicts(table.get("conflicts", defaults.conflicts))
    except ValueError as error:
        message = f"[results] conflicts must be one of {', '.join(c.value for c in Conflicts)}"
        raise ConfigError(message) from error
    return Results(folders["specs"], folders["decisions"], write, conflicts)


def parse_repo_config(text: str) -> RepoConfig:
    """Read a repository's ``.shelf/config.toml``."""
    document = _load(text)
    _only("shelf", document, {"entries", "base_branch", "checks", "policy", "roles", "results"})
    policy = document.get("policy", {})
    _only("policy", policy, {"max_rounds", "spec_approval", "design_review", "proceed_on_deadlock"})
    roles = document.get("roles", {})
    try:
        entries = frozenset(EntryPoint(name) for name in document.get("entries", [e.value for e in EntryPoint]))
        role_map = {Role(name): _names(roles, name) for name in roles}
        built = Policy(**policy)
    except (ValueError, TypeError) as error:
        raise ConfigError(str(error)) from error
    return RepoConfig(
        policy=built,
        entries=entries,
        base_branch=str(document.get("base_branch", "main")),
        checks=tuple(str(check) for check in document.get("checks", [])),
        roles=role_map,
        results=_results(document.get("results", {})),
    )
