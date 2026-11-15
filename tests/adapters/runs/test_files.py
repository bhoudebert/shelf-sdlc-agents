import os
import time
from pathlib import Path

from shelf.adapters.runs.files import FileRunRecords
from shelf.domain.runlog import RunRecord, ToolEvent


def record(work: str = "work-1", phase: str = "plan", attempt: int = 0) -> RunRecord:
    return RunRecord(work, phase, attempt, "planner", "t0", "t1", "finished", tools=(ToolEvent("Bash", "ls"),))


async def test_the_records_of_a_work_come_back_oldest_first(tmp_path: Path) -> None:
    store = FileRunRecords(tmp_path)
    await store.write(record(phase="intake"))
    await store.write(record(phase="plan", attempt=1))
    found = await store.read("work-1")
    assert [(r.phase, r.attempt) for r in found] == [("intake", 0), ("plan", 1)]
    assert await store.read("work-other") == []


async def test_a_work_id_cannot_escape_the_folder(tmp_path: Path) -> None:
    store = FileRunRecords(tmp_path / "runs")
    await store.write(record(work="../../etc"))
    assert not (tmp_path / "etc").exists()
    assert [p.name for p in (tmp_path / "runs").iterdir()] == [".._.._etc"]
    await FileRunRecords(tmp_path / "runs").write(record(work=".."))
    assert (tmp_path / "runs" / "x").is_dir()


async def test_a_store_that_cannot_be_written_never_raises(tmp_path: Path) -> None:
    blocked = tmp_path / "file"
    blocked.write_text("not a folder")
    await FileRunRecords(blocked / "inside").write(record())
    assert await FileRunRecords(blocked / "inside").read("work-1") == []


async def test_a_corrupt_file_is_skipped_and_old_works_are_pruned(tmp_path: Path) -> None:
    store = FileRunRecords(tmp_path, keep_days=30)
    await store.write(record())
    (tmp_path / "work-1" / "999-x-0.json").write_text("{not json")
    assert len(await store.read("work-1")) == 1
    old = tmp_path / "work-old"
    old.mkdir()
    (old / "001-x-0.json").write_text("{}")
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    await store.write(record(work="work-2"))
    assert not old.exists()
    assert (tmp_path / "work-1").exists()
