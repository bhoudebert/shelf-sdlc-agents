import json
from pathlib import Path

import pytest

from shelf.adapters.step_check.check import KEPT, main, run_check
from shelf.domain.stepstream import Check, Event, Hello, StepStream, decode


async def ran(command: str, workdir: Path) -> list[Event]:
    events: list[Event] = []
    await run_check(command, workdir, events.append)
    return events


async def test_a_command_that_passes_says_hello_and_then_its_output(tmp_path: Path) -> None:
    assert await ran("echo hi", tmp_path) == [Hello(), Check(0, "hi\n")]


async def test_a_command_that_fails_reports_its_exit_code_and_what_it_said(tmp_path: Path) -> None:
    assert await ran("echo bad; exit 3", tmp_path) == [Hello(), Check(3, "bad\n")]


async def test_standard_error_is_part_of_the_output(tmp_path: Path) -> None:
    [_, check] = await ran("echo out; echo err 1>&2", tmp_path)
    assert isinstance(check, Check)
    assert "out" in check.output
    assert "err" in check.output


async def test_the_command_runs_in_the_clone(tmp_path: Path) -> None:
    [_, check] = await ran("pwd", tmp_path)
    assert check == Check(0, f"{tmp_path}\n")


async def test_the_command_is_a_shell_command(tmp_path: Path) -> None:
    [_, check] = await ran("echo a && echo b | tr b c", tmp_path)
    assert check == Check(0, "a\nc\n")


async def test_only_the_end_of_a_long_output_is_kept_and_it_is_the_end(tmp_path: Path) -> None:
    [_, check] = await ran("yes x | head -c 200000; echo THE-END; exit 1", tmp_path)
    assert isinstance(check, Check)
    assert check.code == 1
    assert len(check.output) <= KEPT
    assert check.output.endswith("THE-END\n")


async def test_a_command_that_cannot_start_is_a_failed_check_not_a_crash(tmp_path: Path) -> None:
    [_, check] = await ran("definitely-not-a-program-xyz", tmp_path)
    assert isinstance(check, Check)
    assert check.code != 0
    assert "definitely-not-a-program-xyz" in check.output


def test_main_reads_the_task_and_writes_lines_the_worker_reads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"command": "echo done; exit 2"}))

    assert main([str(task)], workdir=tmp_path) == 0  # the step ended well: the check's own result is in its line

    stream = StepStream()
    for line in capsys.readouterr().out.splitlines():
        stream.feed(line)
    assert stream.check == Check(2, "done\n")


def test_a_task_without_a_command_stops_with_a_message_and_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task = tmp_path / "task.json"
    task.write_text("{}")

    assert main([str(task)], workdir=tmp_path) == 1
    captured = capsys.readouterr()
    assert "command" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_what_main_writes_is_only_protocol_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    task = tmp_path / "task.json"
    task.write_text(json.dumps({"command": "echo noise"}))
    main([str(task)], workdir=tmp_path)
    for line in capsys.readouterr().out.splitlines():
        decode(line)
