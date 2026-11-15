"""``RunRecords`` over a folder that the worker writes and the web page reads: a file per run, a folder per work."""

import asyncio
import json
import logging
import os
import re
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from shelf.domain.runlog import RunRecord, from_data, to_data

log = logging.getLogger(__name__)

KEEP_DAYS = 30
"""How long the records of a work are kept after its last run."""
_SAFE = re.compile(r"[A-Za-z0-9._-]{1,80}")


def _safe(name: str) -> str:
    """A name that is one folder name and nothing else: no separator, and never ``.`` or ``..``."""
    cleaned = name if _SAFE.fullmatch(name) else re.sub(r"[^A-Za-z0-9._-]", "_", name)[:80]
    return "x" if not cleaned or set(cleaned) == {"."} else cleaned


@dataclass(frozen=True, slots=True)
class FileRunRecords:
    """The ``RunRecords`` port over a folder."""

    directory: Path
    keep_days: int = KEEP_DAYS

    def _folder(self, work_id: str) -> Path:
        return self.directory / _safe(work_id)

    def _write(self, record: RunRecord) -> None:
        folder = self._folder(record.work_id)
        folder.mkdir(parents=True, exist_ok=True)
        existing = len(list(folder.glob("*.json")))
        name = f"{existing + 1:03d}-{_safe(record.phase)}-{record.attempt}.json"
        descriptor, temporary = tempfile.mkstemp(dir=folder, prefix=".run.")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(to_data(record), handle, indent=1)
            Path(temporary).chmod(0o644)
            Path(temporary).replace(folder / name)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - self.keep_days * 86400
        for folder in self.directory.iterdir():
            try:
                if folder.is_dir() and folder.stat().st_mtime < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
            except OSError:
                continue

    def _read(self, work_id: str) -> list[RunRecord]:
        folder = self._folder(work_id)
        if not folder.is_dir():
            return []
        records: list[RunRecord] = []
        for path in sorted(folder.glob("*.json")):
            try:
                records.append(from_data(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError, KeyError, IndexError):
                continue
        return records

    async def write(self, record: RunRecord) -> None:
        """Keep ``record``; a store that cannot be written is logged and never stops a step."""
        try:
            await asyncio.to_thread(self._write, record)
        except OSError:
            log.warning("could not keep the record of a run of %s", record.work_id, exc_info=True)

    async def read(self, work_id: str) -> Sequence[RunRecord]:
        """The records of a work, oldest first; none when there are none."""
        try:
            return await asyncio.to_thread(self._read, work_id)
        except OSError:
            return []
