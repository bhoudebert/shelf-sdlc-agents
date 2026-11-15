"""Which tool versions a repository's CI uses, read from its workflows and version files. Pure."""

import json
import re
from collections.abc import Mapping
from typing import cast

DECLARED = (
    "mise.toml",
    ".mise.toml",
    ".tool-versions",
    "mise/config.toml",
    ".config/mise.toml",
    ".config/mise/config.toml",
)
"""Where a repository says it uses mise: then its own declaration wins, and nothing is detected."""

SOURCES = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".nvmrc",
    ".node-version",
    ".python-version",
    "package.json",
    "go.mod",
    "flake.nix",
)
"""The files read to find the versions, as glob patterns."""

TOOLS = ("node", "python", "go", "java")
"""The only tools installed from what a repository says: the ones every CI sets up, and nothing it names itself."""

_VERSION = re.compile(r"(?:\d{1,3}(?:\.\d{1,3}){0,2}|lts)")
_USES = re.compile(r"^\s*-?\s*uses:\s*['\"]?actions/(setup-node|setup-python|setup-go|setup-java)@", re.MULTILINE)
_KEY = re.compile(r"^\s*(?:-\s*)?([A-Za-z0-9_-]+):\s*(.*?)\s*$")
_STEP_START = re.compile(r"^\s*-\s+(?:name|uses|run|id|if|env|with):")
_ACTION_TOOL = {
    "setup-node": ("node", ("node-version", "node-version-file")),
    "setup-python": ("python", ("python-version", "python-version-file")),
    "setup-go": ("go", ("go-version", "go-version-file")),
    "setup-java": ("java", ("java-version",)),
}
_LOOK_AHEAD = 14


def plain(value: str) -> str | None:
    """``value`` as a version a tool can be installed at: a number (a leading ``v`` or a ``.x`` allowed), or ``lts``."""
    cleaned = value.strip().strip("'\"").strip()
    if cleaned.lower().startswith("lts"):
        return "lts"
    cleaned = re.sub(r"\.(?:x|\*)$", "", cleaned.removeprefix("v"))
    return cleaned if _VERSION.fullmatch(cleaned) else None


def _from_range(spec: str) -> str | None:
    """The first plain version in a range such as ``>=24``, ``^22.1`` or ``24.x``; ``None`` when there is none."""
    found = re.search(r"\d{1,3}(?:\.\d{1,3}){0,2}", spec)
    return found.group(0) if found and not re.search(r"[|]{2}|\s-\s", spec) else None


def _workflow_versions(text: str, files: Mapping[str, str]) -> dict[str, str]:
    found: dict[str, str] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = _USES.match(line)
        if not match:
            continue
        tool, keys = _ACTION_TOOL[match.group(1)]
        if tool in found:
            continue
        for follower in lines[index + 1 : index + 1 + _LOOK_AHEAD]:
            if _STEP_START.match(follower) and not follower.strip().startswith("with:"):
                break
            pair = _KEY.match(follower)
            if not pair or pair.group(1) not in keys:
                continue
            value = pair.group(2).split(" #")[0].strip()
            is_file = pair.group(1).endswith("-file")
            version = _from_file(value.strip("'\""), files, tool) if is_file else plain(value)
            if version:
                found[tool] = _java_major(version) if tool == "java" else version
                break
    return found


def _java_major(version: str) -> str:
    return version.split(".", maxsplit=1)[0]


def _from_file(name: str, files: Mapping[str, str], tool: str) -> str | None:
    text = files.get(name)
    if text is None:
        return None
    if name.endswith("go.mod"):
        return _go_mod(text)
    first = next((line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")), "")
    return plain(first) if tool in ("node", "python") else None


def _go_mod(text: str) -> str | None:
    match = re.search(r"^go\s+(\d{1,3}\.\d{1,3}(?:\.\d{1,3})?)\s*$", text, re.MULTILINE)
    return match.group(1) if match else None


def _package_json_node(text: str) -> str | None:
    try:
        document: object = json.loads(text)
    except ValueError:
        return None
    engines = cast("dict[str, object]", document).get("engines") if isinstance(document, dict) else None
    spec = cast("dict[str, object]", engines).get("node") if isinstance(engines, dict) else None
    return _from_range(spec) if isinstance(spec, str) else None


def is_declared(files: Mapping[str, str]) -> bool:
    """Whether the repository declares its tools for mise, so that nothing is to be detected."""
    return any(name in files for name in DECLARED)


def detect_tools(files: Mapping[str, str]) -> dict[str, str]:
    """The versions of node, python, go and java the repository's CI uses, from ``files`` (path to text).

    A workflow's setup step wins over a version file, because CI is what decides whether the work is green. Nothing is
    returned for a repository that declares its tools for mise, and nothing that is not a plain version number.
    """
    if is_declared(files):
        return {}
    found: dict[str, str] = {}
    for name in sorted(files):
        if name.startswith(".github/workflows/"):
            for tool, version in _workflow_versions(files[name], files).items():
                found.setdefault(tool, version)
    for tool, name in (("node", ".nvmrc"), ("node", ".node-version"), ("python", ".python-version")):
        if tool not in found and name in files and (version := _from_file(name, files, tool)):
            found[tool] = version
    if "node" not in found and "package.json" in files and (version := _package_json_node(files["package.json"])):
        found["node"] = version
    if "go" not in found and "go.mod" in files and (version := _go_mod(files["go.mod"])):
        found["go"] = version
    return {tool: found[tool] for tool in TOOLS if tool in found}
