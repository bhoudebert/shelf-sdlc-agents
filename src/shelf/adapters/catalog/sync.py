"""Fetch the catalog's sources at their pinned commits and lay them out for the worker. Nothing fetched is ever run."""

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shelf.domain.catalog import Catalog, CatalogError, Kind, Source, managed_policy, marketplace

LOCK = "catalog.lock.json"
POLICY = "managed-settings.json"
_GIT_ENV = {"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}


@dataclass(frozen=True, slots=True)
class Synced:
    """What one source produced: the skills (or the plugin) and every command its hooks would run."""

    source: Source
    produced: tuple[str, ...]
    hooks: tuple[str, ...] = ()


def _git(args: list[str], cwd: Path) -> None:
    # No hooks of the fetched repository can run: the clone is fresh and hooks are pointed at nothing.
    command = ["git", "-c", f"core.hooksPath={os.devnull}", *args]
    subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True, env={**os.environ, **_GIT_ENV})  # noqa: S603


def _fetch(source: Source, into: Path) -> Path:
    """The source's files at its commit, in a fresh directory; the path inside the repository is where it is rooted."""
    into.mkdir(parents=True)
    try:
        _git(["init", "-q"], into)
        _git(["fetch", "-q", "--depth", "1", source.git, source.ref], into)
        _git(["checkout", "-q", "--detach", "FETCH_HEAD"], into)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()[-1:] or ["git failed"]
        message = f"source {source.name}: cannot fetch commit {source.ref} from {source.git}: {detail[0]}"
        raise CatalogError(message) from error
    root = (into / source.path).resolve()
    if not root.is_dir() or into.resolve() not in (root, *root.parents):
        message = f"source {source.name}: the path {source.path or '.'} is not a folder of the repository"
        raise CatalogError(message)
    return root


def _copy(source: Path, target: Path) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"), symlinks=False)


def _commands(node: Any) -> list[str]:  # noqa: ANN401 - a parsed JSON document has no more precise type
    """Every ``command`` string in a hooks document, wherever it is nested."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():  # pyright: ignore[reportUnknownVariableType]
            if key == "command" and isinstance(value, str):
                found.append(value)
            else:
                found += _commands(value)
    elif isinstance(node, list):
        for item in node:  # pyright: ignore[reportUnknownVariableType]
            found += _commands(item)
    return found


def hook_commands(plugin: Path) -> tuple[str, ...]:
    """The commands a plugin's hooks would run, from its manifest and its hooks file. Best effort, never executed."""
    documents: list[Any] = []
    manifest = plugin / ".claude-plugin" / "plugin.json"
    try:
        declared = json.loads(manifest.read_text(encoding="utf-8")).get("hooks")
    except (OSError, ValueError, AttributeError):
        declared = None
    candidates = [plugin / "hooks" / "hooks.json"]
    for item in declared if isinstance(declared, list) else [declared]:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(item, str):
            candidates.append(plugin / item)
        elif isinstance(item, dict):
            documents.append(item)
    for candidate in candidates:
        try:
            documents.append(json.loads(candidate.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return tuple(dict.fromkeys(command for document in documents for command in _commands(document)))


def _plugin(source: Source, root: Path, stage: Path) -> Synced:
    if not (root / ".claude-plugin" / "plugin.json").is_file():
        where = source.path or "the top of the repository"
        message = f"source {source.name}: a plugin needs .claude-plugin/plugin.json at {where}"
        raise CatalogError(message)
    _copy(root, stage / source.name)
    return Synced(source, (source.name,), hook_commands(stage / source.name))


def _skill_folders(root: Path) -> dict[str, Path]:
    if (root / "SKILL.md").is_file():
        return {root.name: root}
    found = sorted(p.parent for p in root.rglob("SKILL.md") if "node_modules" not in p.parts)
    return {folder.name: folder for folder in found}


def _skills(source: Source, root: Path, stage: Path) -> Synced:
    folders = _skill_folders(root)
    if not folders:
        message = f"source {source.name}: no folder with a SKILL.md under {source.path or 'the repository'}"
        raise CatalogError(message)
    wanted = source.skills or tuple(folders)
    missing = [name for name in wanted if name not in folders]
    if missing:
        message = f"source {source.name}: no skill named {', '.join(missing)} (found: {', '.join(folders)})"
        raise CatalogError(message)
    plugin = stage / source.name
    manifest = {
        "name": source.name,
        "version": source.ref[:7],
        "description": f"Skills of {source.git} at {source.ref}",
    }
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for name in wanted:
        _copy(folders[name], plugin / "skills" / name)
    return Synced(source, tuple(wanted))


def _lock(synced: list[Synced]) -> dict[str, Any]:
    return {
        "sources": {
            item.source.name: {
                "git": item.source.git,
                "ref": item.source.ref,
                "kind": item.source.kind.value,
                "path": item.source.path,
                "produced": list(item.produced),
                "hooks": list(item.hooks),
            }
            for item in synced
        }
    }


def _replace(target: Path, staged: Path) -> None:
    """Put ``staged``'s content into ``target`` (often a mounted volume, so the folder itself stays)."""
    target.mkdir(parents=True, exist_ok=True)
    for child in target.iterdir():
        shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
    shutil.copytree(staged, target, dirs_exist_ok=True)


def sync(catalog: Catalog, plugins_out: Path, policy_out: Path, runtime_dir: str) -> list[Synced]:
    """Fetch every source and replace the catalog; any failure raises before the catalog on disk is touched."""
    with tempfile.TemporaryDirectory(prefix="shelf-catalog-") as scratch:
        base = Path(scratch)
        stage, policy = base / "plugins", base / "policy"
        stage.mkdir()
        policy.mkdir()
        synced: list[Synced] = []
        for source in catalog.sources:
            root = _fetch(source, base / "fetched" / source.name)
            synced.append(_plugin(source, root, stage) if source.kind is Kind.PLUGIN else _skills(source, root, stage))
        corporate = [item.source for item in synced if item.source.kind is Kind.PLUGIN]
        (stage / ".claude-plugin").mkdir()
        (stage / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(marketplace(corporate), indent=2) + "\n", encoding="utf-8"
        )
        (stage / LOCK).write_text(json.dumps(_lock(synced), indent=2) + "\n", encoding="utf-8")
        (policy / POLICY).write_text(
            json.dumps(managed_policy(corporate, catalog.hooks, runtime_dir), indent=2) + "\n", encoding="utf-8"
        )
        _replace(plugins_out, stage)
        _replace(policy_out, policy)
        return synced
