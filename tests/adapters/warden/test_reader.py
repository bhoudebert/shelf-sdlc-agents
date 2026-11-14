import stat
from pathlib import Path

import pytest

from shelf.adapters.warden.reader import WardenReader
from shelf.domain.guard import GuardReport
from shelf.domain.result import Err, Ok

REPORT = (
    '{"records":9,"calls":7,"would_stop":3,"by_category":{"destructive":2,"exfil":1},'
    '"by_decision":{"allow":6,"deny":3},"redactions":{"secret":2,"email":3}}'
)


def fake_warden(tmp_path: Path, report: str, verify_status: int) -> str:
    script = tmp_path / "warden"
    script.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = report ]; then printf %s \'{report}\'; exit 0; fi\n'
        f"if [ \"$1\" = audit ]; then exit {verify_status}; fi\n"
        "exit 2\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.mark.anyio
async def test_the_counts_come_from_the_guards_own_report(tmp_path: Path) -> None:
    result = await WardenReader(fake_warden(tmp_path, REPORT, 0)).report()
    assert result == Ok(GuardReport(7, 3, 5, chain_intact=True, categories={"destructive": 2, "exfil": 1}))


@pytest.mark.anyio
async def test_a_broken_chain_is_reported(tmp_path: Path) -> None:
    result = await WardenReader(fake_warden(tmp_path, REPORT, 1)).report()
    assert isinstance(result, Ok)
    assert not result.value.chain_intact


@pytest.mark.anyio
async def test_a_missing_binary_is_a_sentence_not_an_exception(tmp_path: Path) -> None:
    assert await WardenReader(str(tmp_path / "nope")).report() == Err("the guard is not installed")


@pytest.mark.anyio
async def test_an_answer_this_version_cannot_read_is_a_sentence(tmp_path: Path) -> None:
    result = await WardenReader(fake_warden(tmp_path, "[1]", 0)).report()
    assert isinstance(result, Err)
    assert "does not understand" in result.error


def test_the_most_frequent_risks_come_first() -> None:
    report = GuardReport(1, 1, 0, chain_intact=True, categories={"b": 2, "a": 2, "c": 5})
    assert report.top_categories(2) == (("c", 5), ("a", 2))
