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


SANDBOX_BEGIN = "# shelf: sandbox placeholders, local to this run and never committed"
SANDBOX_END = "# shelf: end of the sandbox placeholders"
SANDBOX_PLACEHOLDERS = (
    ".bash_profile",
    ".bashrc",
    ".claude/",
    ".gitconfig",
    ".gitmodules",
    ".idea",
    ".profile",
    ".ripgreprc",
    ".vscode",
    ".zprofile",
    ".zshrc",
)
"""What the agents' sandbox shows in the working directory, unreadable: Prettier fails on each of them."""

SANDBOX_NOTE = (
    "The sandbox shows some dotfiles and folders in the repository folder as unreadable (`.bashrc`, `.profile`, "
    "`.gitconfig`, `.vscode`, `.idea`, `.claude/`...): they are not part of the repository or of your change. "
    "The system has made `.prettierignore` skip them for this run only, so `prettier --check .` and the repository's "
    "scripts can run; it removes that block before anything is committed. Never add them to the repository."
)


def without_sandbox_placeholders(text: str) -> str:
    """``text`` without the block that ignores the sandbox's placeholders; unchanged when there is none."""
    lines = text.splitlines()
    if SANDBOX_BEGIN not in lines:
        return text
    start = lines.index(SANDBOX_BEGIN)
    end = lines.index(SANDBOX_END, start) if SANDBOX_END in lines[start:] else len(lines) - 1
    kept = [*lines[: max(0, start - 1) if start and not lines[start - 1].strip() else start], *lines[end + 1 :]]
    return "\n".join(kept) + ("\n" if kept else "")


def with_sandbox_placeholders(existing: str | None) -> str:
    """The ``.prettierignore`` with the block that ignores the sandbox's placeholders; the block once, at the end."""
    base = without_sandbox_placeholders(existing or "").rstrip("\n")
    block = "\n".join([SANDBOX_BEGIN, *SANDBOX_PLACEHOLDERS, SANDBOX_END])
    return f"{base}\n\n{block}\n" if base else f"{block}\n"
