"""Keeping Shelf's own files out of a repository's formatter, so that a whole-repository check never fails on them."""

import re
from collections.abc import Mapping

IGNORE_FILE = ".prettierignore"
FOLDER = ".shelf/"
CONFIG_FILES = (
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    ".prettierrc.json5",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.mjs",
    ".prettierrc.toml",
    "prettier.config.js",
    "prettier.config.cjs",
    "prettier.config.mjs",
)
READ = (IGNORE_FILE, *CONFIG_FILES, "package.json")
"""The files looked at, so that the caller reads only these."""

_IGNORING = frozenset(
    {".shelf", "/.shelf", ".shelf/", "/.shelf/", ".shelf/**", "/.shelf/**", "**/.shelf", "**/.shelf/**"}
)


def uses_prettier(files: Mapping[str, str]) -> bool:
    """Whether the repository uses Prettier: a configuration file, an ignore file, or the package in its manifest."""
    if any(name in files for name in (IGNORE_FILE, *CONFIG_FILES)):
        return True
    return bool(re.search(r'"prettier"\s*:', files.get("package.json", "")))


def prettier_ignore(files: Mapping[str, str]) -> str | None:
    """The new ``.prettierignore`` that keeps ``.shelf/`` out of Prettier, or ``None`` when nothing is to change.

    Nothing changes for a repository that does not use Prettier, or that already ignores the folder.
    """
    if not uses_prettier(files):
        return None
    existing = files.get(IGNORE_FILE)
    if existing is not None and any(line.strip() in _IGNORING for line in existing.splitlines()):
        return None
    kept = existing.rstrip("\n") + "\n\n" if existing and existing.strip() else ""
    return f"{kept}# Shelf's own files for each piece of work\n{FOLDER}\n"
