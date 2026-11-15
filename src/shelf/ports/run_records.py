"""Where the records of agent runs are kept, so that a work can be diagnosed after the worker is gone."""

from collections.abc import Sequence
from typing import Protocol

from shelf.domain.runlog import RunRecord


class RunRecords(Protocol):
    """Keeps and reads what each agent run did."""

    async def write(self, record: RunRecord) -> None:
        """Keep ``record``. Never raises for a full or unwritable store: a record is a courtesy."""
        ...

    async def read(self, work_id: str) -> Sequence[RunRecord]:
        """The records of a work, oldest first; none when there are none or the store cannot be read."""
        ...
