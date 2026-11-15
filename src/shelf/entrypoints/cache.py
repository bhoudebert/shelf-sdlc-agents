"""``shelf-cache``: look after the folder the agents' tools and package caches live in."""

import argparse
import os
import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path

DAYS = 30
MARKER = ".shelf-used"
"""Touched by the worker each time an agent runs in a home: when it was last used."""


def last_used(home: Path) -> float:
    """When ``home`` was last used: its marker if it has one, else the folder itself."""
    marker = home / MARKER
    return (marker if marker.exists() else home).stat().st_mtime


def size_of(home: Path) -> int:
    """The bytes under ``home``, without following links out of it."""
    total = 0
    for root, _, files in os.walk(home, followlinks=False):
        for name in files:
            path = Path(root, name)
            if not path.is_symlink():
                total += path.stat().st_size
    return total


def prune(cache: Path, days: int, now: float, *, dry_run: bool = False) -> list[tuple[Path, int]]:
    """Remove the home of every repository unused for ``days`` days; return what went with its size in bytes.

    Only folders directly under ``<cache>/home`` are ever touched, and never a link.
    """
    homes = cache / "home"
    if not homes.is_dir():
        return []
    gone: list[tuple[Path, int]] = []
    for home in sorted(homes.iterdir()):
        if home.is_symlink() or not home.is_dir() or now - last_used(home) < days * 86400:
            continue
        gone.append((home, size_of(home)))
        if not dry_run:
            shutil.rmtree(home)
    return gone


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``shelf-cache``."""
    parser = argparse.ArgumentParser(prog="shelf-cache", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pruning = commands.add_parser("prune", help="remove the homes of repositories nothing used for a while")
    pruning.add_argument("--older-than", type=int, default=DAYS, metavar="DAYS", help=f"default {DAYS}")
    pruning.add_argument("--dry-run", action="store_true", help="say what would go, remove nothing")
    args = parser.parse_args(argv)
    directory = os.environ.get("SHELF_CACHE_DIR", "").strip()
    if not directory:
        print("SHELF_CACHE_DIR is not set: there is no cache to prune.", file=sys.stderr)  # noqa: T201
        return 1
    gone = prune(Path(directory), args.older_than, time.time(), dry_run=args.dry_run)
    verb = "would remove" if args.dry_run else "removed"
    for path, size in gone:
        print(f"{verb} {path.name} ({size / 1_000_000:.1f} MB)")  # noqa: T201
    freed = sum(size for _, size in gone) / 1_000_000
    print(f"{verb} {len(gone)} homes, {freed:.1f} MB")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
