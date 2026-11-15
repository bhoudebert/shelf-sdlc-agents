"""The overlay of the guard, kept in a folder: the list of rules, the file the guard reads, and a log of the changes."""

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from shelf.domain.guard_rules import OverlayRule, RuleKind, allowed_sites, render

RULES_FILE = "rules.json"
OVERLAY_FILE = "warden.ui.toml"
CHANGES_FILE = "changes.jsonl"


def _replace(path: Path, text: str) -> None:
    """Write ``text`` as the whole of ``path``: a new file renamed over the old, so a reader never sees half of it."""
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(temporary).chmod(0o644)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


@dataclass(frozen=True, slots=True)
class FileGuardRules:
    """The ``GuardRules`` port over a folder that this service writes and the worker reads."""

    directory: Path
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def overlay_file(self) -> Path:
        """The file the guard reads."""
        return self.directory / OVERLAY_FILE

    def _load(self) -> tuple[OverlayRule, ...]:
        path = self.directory / RULES_FILE
        if not path.is_file():
            return ()
        return tuple(
            OverlayRule(item["id"], RuleKind(item["kind"]), item["subject"], item["by"], item["at"])
            for item in json.loads(path.read_text(encoding="utf-8"))
        )

    def _save(self, rules: tuple[OverlayRule, ...]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        listed = [{"id": r.id, "kind": r.kind.value, "subject": r.subject, "by": r.by, "at": r.at} for r in rules]
        _replace(self.directory / RULES_FILE, json.dumps(listed, indent=2) + "\n")
        _replace(self.overlay_file, render(rules))

    def _log(self, what: str, rule: OverlayRule, by: str, at: str) -> None:
        entry = {"at": at, "by": by, "change": what, "rule": rule.id, "kind": rule.kind.value, "subject": rule.subject}
        with (self.directory / CHANGES_FILE).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def sites_now(self) -> tuple[str, ...]:
        """The sites added from the page, read from the folder now; none when it cannot be read."""
        try:
            return allowed_sites(self._load())
        except (OSError, ValueError, KeyError):
            return ()

    async def rules(self) -> tuple[OverlayRule, ...]:
        """The rules in force, oldest first."""
        return await asyncio.to_thread(self._load)

    async def add(self, rule: OverlayRule) -> None:
        """Keep ``rule`` and rewrite the overlay; the same rule twice changes nothing."""
        async with self._lock:
            current = await asyncio.to_thread(self._load)
            if any(existing.id == rule.id for existing in current):
                return
            await asyncio.to_thread(self._save, (*current, rule))
            await asyncio.to_thread(self._log, "added", rule, rule.by, rule.at)

    async def remove(self, rule_id: str, by: str, at: str) -> bool:
        """Take a rule out of the overlay and say so in the log."""
        async with self._lock:
            current = await asyncio.to_thread(self._load)
            gone = next((rule for rule in current if rule.id == rule_id), None)
            if gone is None:
                return False
            await asyncio.to_thread(self._save, tuple(rule for rule in current if rule.id != rule_id))
            await asyncio.to_thread(self._log, "removed", gone, by, at)
            return True
