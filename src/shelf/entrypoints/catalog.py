"""``shelf-catalog sync``: fetch the operator's catalog at its pinned commits and lay it out for the worker."""

import argparse
import os
import sys
from dataclasses import replace
from pathlib import Path

from shelf.adapters.catalog.sync import LOCK, sync
from shelf.domain.catalog import CatalogError, Kind, guard_hooks, parse_catalog

RUNTIME_DIR = "/opt/shelf/catalog"
"""Where the worker mounts the synced plugins; the managed policy points its marketplace here."""

WARDEN_BINARY = "/usr/local/bin/warden"
"""Where the image puts Warden, the guard around every agent."""


def run(config: Path, plugins_out: Path, policy_out: Path, runtime_dir: str, guard: str = "") -> int:
    """Sync and report; the exit code is zero only when the whole catalog was fetched and valid.

    ``guard`` is the path of Warden: when given, its hooks come first in the managed policy and run for every agent.
    """
    try:
        catalog = parse_catalog(config.read_text(encoding="utf-8") if config.exists() else "")
        if guard:
            catalog = replace(catalog, hooks=(*guard_hooks(guard), *catalog.hooks))
        synced = sync(catalog, plugins_out, policy_out, runtime_dir)
    except CatalogError as error:
        print(f"catalog: {error}", file=sys.stderr)  # noqa: T201
        return 1
    for item in synced:
        kind = "plugin" if item.source.kind is Kind.PLUGIN else "skills"
        print(f"catalog: {item.source.name} ({kind}) at {item.source.ref[:12]}: {', '.join(item.produced)}")  # noqa: T201
        for command in item.hooks:
            print(f"catalog:   its hooks run: {command}")  # noqa: T201
    if guard:
        print(f"catalog: warden ({guard}) guards every agent; its hooks block a call if warden fails")  # noqa: T201
    for hook in catalog.hooks[len(guard_hooks(guard)) if guard else 0 :]:
        print(f"catalog: operator hook on {hook.event}: {hook.command}")  # noqa: T201
    print(f"catalog: {len(synced)} source(s) synced; the lock is {plugins_out / LOCK}")  # noqa: T201
    return 0


def main() -> None:
    """Console entry point: ``shelf-catalog``."""
    parser = argparse.ArgumentParser(prog="shelf-catalog")
    parser.add_argument("command", choices=["sync"])
    parser.add_argument("--config", type=Path, default=Path("/etc/shelf/catalog.toml"))
    parser.add_argument("--plugins-out", type=Path, default=Path(RUNTIME_DIR))
    parser.add_argument("--policy-out", type=Path, default=Path("/etc/claude-code"))
    parser.add_argument("--runtime-dir", default=RUNTIME_DIR)
    parser.add_argument("--warden", type=Path, default=Path(WARDEN_BINARY), help="the path of warden, the guard")
    arguments = parser.parse_args()
    on = os.environ.get("SHELF_WARDEN", "on").strip().lower() not in {"off", "0", "false", "no"}
    guard = str(arguments.warden) if on and arguments.warden.is_file() else ""
    if on and not guard:
        print(f"catalog: warden is not at {arguments.warden}: agents run without its guard", file=sys.stderr)  # noqa: T201
    sys.exit(run(arguments.config, arguments.plugins_out, arguments.policy_out, arguments.runtime_dir, guard))


if __name__ == "__main__":
    main()
