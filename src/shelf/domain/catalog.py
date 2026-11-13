"""The operator's catalog of skills and plugins: what it may contain, and what is generated from it. Pure."""

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Final

MARKETPLACE: Final = "shelf-corp"
"""The name of the generated local marketplace the corporate plugins are registered in."""

_SLUG: Final = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
_COMMIT: Final = re.compile(r"[0-9a-f]{40}")
_KEYS: Final = frozenset({"name", "git", "ref", "kind", "path", "skills"})
_HOOK_KEYS: Final = frozenset({"event", "matcher", "command"})


class CatalogError(ValueError):
    """The catalog is not valid, and says which source and why."""


class Kind(StrEnum):
    """What a source is taken as."""

    SKILLS = "skills"
    """Only its skill folders, as a plugin without hooks, loaded for the roles the operator binds it to."""
    PLUGIN = "plugin"
    """The whole plugin, hooks included, enabled for every agent through the managed policy."""


@dataclass(frozen=True, slots=True)
class Source:
    """One repository, at one commit, taken as one kind."""

    name: str
    git: str
    ref: str
    kind: Kind
    path: str = ""
    skills: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Hook:
    """A command the operator runs at an event of every agent, written by the operator and never fetched."""

    event: str
    command: str
    matcher: str = ""


@dataclass(frozen=True, slots=True)
class Catalog:
    """What the operator's ``catalog.toml`` holds."""

    sources: tuple[Source, ...] = ()
    hooks: tuple[Hook, ...] = ()


def _text(entry: Mapping[str, Any], key: str, name: str) -> str:
    value = entry.get(key, "")
    if not isinstance(value, str):
        message = f"source {name}: {key} must be text"
        raise CatalogError(message)
    return value


def _source(entry: Mapping[str, Any], seen: set[str]) -> Source:
    name = _text(entry, "name", "?")
    label = name or "?"
    if not _SLUG.fullmatch(name):
        message = f"source {label}: the name must be lower-case letters, digits and dashes"
        raise CatalogError(message)
    if name in seen:
        message = f"source {name}: another source has this name"
        raise CatalogError(message)
    unknown = set(entry) - _KEYS
    if unknown:
        message = f"source {name}: unknown keys {', '.join(sorted(unknown))}"
        raise CatalogError(message)
    git = _text(entry, "git", name)
    if not git:
        message = f"source {name}: git is required"
        raise CatalogError(message)
    ref = _text(entry, "ref", name)
    if not _COMMIT.fullmatch(ref):
        message = (
            f"source {name}: ref must be a full 40-character commit, not a branch or a tag (got {ref or 'nothing'})"
        )
        raise CatalogError(message)
    try:
        kind = Kind(_text(entry, "kind", name))
    except ValueError as error:
        message = f"source {name}: kind must be one of {', '.join(k.value for k in Kind)}"
        raise CatalogError(message) from error
    path = _text(entry, "path", name)
    parts = PurePosixPath(path).parts
    if PurePosixPath(path).is_absolute() or ".." in parts:
        message = f"source {name}: path must stay inside the repository"
        raise CatalogError(message)
    skills = entry.get("skills", [])
    if not isinstance(skills, list) or not all(isinstance(s, str) and s for s in skills):  # pyright: ignore[reportUnknownVariableType]
        message = f"source {name}: skills must be a list of folder names"
        raise CatalogError(message)
    return Source(name, git, ref, kind, "/".join(parts), tuple(skills))  # pyright: ignore[reportUnknownArgumentType]


def _hook(entry: Mapping[str, Any], number: int) -> Hook:
    unknown = set(entry) - _HOOK_KEYS
    if unknown:
        message = f"hook {number}: unknown keys {', '.join(sorted(unknown))}"
        raise CatalogError(message)
    values = {key: entry.get(key, "") for key in _HOOK_KEYS}
    if not all(isinstance(value, str) for value in values.values()):
        message = f"hook {number}: event, matcher and command must be text"
        raise CatalogError(message)
    if not values["event"] or not values["command"]:
        message = f"hook {number}: an event and a command are required"
        raise CatalogError(message)
    return Hook(values["event"], values["command"], values["matcher"])


def parse_catalog(text: str) -> Catalog:
    """Read ``catalog.toml``: the sources and hooks in the order written, or an error naming the one that is wrong."""
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        message = f"catalog.toml is not valid TOML: {error}"
        raise CatalogError(message) from error
    unknown = set(document) - {"source", "hook"}
    if unknown:
        message = f"catalog.toml: unknown keys {', '.join(sorted(unknown))}; write [[source]] and [[hook]]"
        raise CatalogError(message)
    entries = document.get("source", [])
    if not isinstance(entries, list):
        message = "catalog.toml: sources are written as [[source]]"
        raise CatalogError(message)
    seen: set[str] = set()
    sources: list[Source] = []
    for entry in entries:  # pyright: ignore[reportUnknownVariableType]
        source = _source(entry, seen)  # pyright: ignore[reportUnknownArgumentType]
        seen.add(source.name)
        sources.append(source)
    hooks = document.get("hook", [])
    if not isinstance(hooks, list):
        message = "catalog.toml: hooks are written as [[hook]]"
        raise CatalogError(message)
    return Catalog(tuple(sources), tuple(_hook(entry, number) for number, entry in enumerate(hooks, 1)))  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]


def marketplace(plugins: Sequence[Source]) -> dict[str, Any]:
    """The generated marketplace that lists the corporate plugins, each at ``./<name>`` beside the file."""
    return {
        "name": MARKETPLACE,
        "owner": {"name": "operator"},
        "plugins": [
            {"name": source.name, "source": f"./{source.name}", "description": f"{source.git} at {source.ref}"}
            for source in plugins
        ],
    }


def managed_policy(plugins: Sequence[Source], hooks: Sequence[Hook], runtime_dir: str) -> dict[str, Any]:
    """The managed policy: only managed hooks run (the operator's and the plugins'), plugins from the marketplace."""
    policy: dict[str, Any] = {"allowManagedHooksOnly": True}
    if hooks:
        events: dict[str, list[dict[str, Any]]] = {}
        for hook in hooks:
            group: dict[str, Any] = {"hooks": [{"type": "command", "command": hook.command}]}
            if hook.matcher:
                group["matcher"] = hook.matcher
            events.setdefault(hook.event, []).append(group)
        policy["hooks"] = events
    if plugins:
        policy["extraKnownMarketplaces"] = {MARKETPLACE: {"source": {"source": "directory", "path": runtime_dir}}}
        policy["enabledPlugins"] = {f"{source.name}@{MARKETPLACE}": True for source in plugins}
    return policy
