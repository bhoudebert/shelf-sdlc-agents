"""Reading what a repository declares for mise, and keeping from it only what is safe to install. Pure.

The worker installs outside the agents' sandbox, so it never runs the declaration itself (its hooks, plugins,
environment scripts or tool options): it reads the tools and their versions and installs those, nothing else.
"""

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

CONFIG_FILES = ("mise.toml", ".mise.toml", "mise/config.toml", ".config/mise.toml", ".config/mise/config.toml")
TOOL_VERSIONS = ".tool-versions"
NO_CODE_AT_INSTALL = "asdf,vfox,npm,pipx,cargo,gem,go,spm"
"""The backends that run the code of a plugin or a package at install time: disabled for what the worker installs."""

_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~-]{0,63}")
MAX_TOOLS = 20


@dataclass(frozen=True, slots=True)
class Declared:
    """The tools to install, and what was left out and why."""

    tools: Mapping[str, str]
    ignored: tuple[str, ...] = ()


def _version_of(value: object) -> str | None:
    """A plain version from a string, a list of strings (the first one) or a table that holds only ``version``."""
    if isinstance(value, str):
        return value if _VERSION.fullmatch(value) else None
    if isinstance(value, list) and value:
        return _version_of(cast("list[object]", value)[0])
    if isinstance(value, dict):
        table = cast("dict[str, object]", value)
        return _version_of(table.get("version")) if set(table) == {"version"} else None
    return None


def _from_toml(text: str) -> Declared:
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return Declared({}, ("the declaration is not valid TOML",))
    section = document.get("tools")
    if not isinstance(section, dict):
        return Declared({})
    tools = cast("dict[str, object]", section)
    kept: dict[str, str] = {}
    ignored: list[str] = []
    for label, value in tools.items():
        version = _version_of(value)
        if not _NAME.fullmatch(label):
            ignored.append(f"{label[:40]}: not a plain tool name (a backend or an address)")
        elif version is None:
            ignored.append(f"{label}: not a plain version (an option or a table runs code)")
        elif len(kept) >= MAX_TOOLS:
            ignored.append(f"{label}: more than {MAX_TOOLS} tools")
        else:
            kept[label] = version
    return Declared(kept, tuple(ignored))


def _from_tool_versions(text: str) -> Declared:
    kept: dict[str, str] = {}
    ignored: list[str] = []
    for line in text.splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) < 2:  # noqa: PLR2004 - a name and a version
            continue
        name, version = parts[0], parts[1]
        if _NAME.fullmatch(name) and _VERSION.fullmatch(version) and len(kept) < MAX_TOOLS:
            kept[name] = version
        else:
            ignored.append(f"{name[:40]}: not a plain tool and version")
    return Declared(kept, tuple(ignored))


def declared_tools(files: Mapping[str, str]) -> Declared:
    """The tools a repository declares for mise, from its ``mise.toml`` (or ``.tool-versions``); the first file wins."""
    for name in CONFIG_FILES:
        if name in files:
            return _from_toml(files[name])
    if TOOL_VERSIONS in files:
        return _from_tool_versions(files[TOOL_VERSIONS])
    return Declared({})


def ignored_sections(files: Mapping[str, str]) -> tuple[str, ...]:
    """The parts of a declaration that would run code if mise ran it, and that the worker therefore does not."""
    for name in CONFIG_FILES:
        if name in files:
            try:
                document = tomllib.loads(files[name])
            except tomllib.TOMLDecodeError:
                return ()
            return tuple(section for section in ("hooks", "plugins", "env", "tasks") if section in document)
    return ()
