import json
import os
from pathlib import Path

import pytest

from shelf.adapters.step_check.check import KEPT, collapse_progress, main, run_check
from shelf.domain.stepstream import Check, Event, Hello, StepStream, decode


@pytest.fixture(autouse=True)
def no_docker_of_the_machine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Docker of the machine that runs the tests is not the step's own: a daemon that never answers, unless a test says so."""
    bin_dir = tmp_path / "no-docker"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text("#!/bin/sh\nexit 1\n")
    (bin_dir / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")


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


def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, containers: str = "", info_ok: bool = True) -> Path:
    """A ``docker`` on the path that knows a few containers; every call is logged."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "containers.tsv").write_text(containers)
    (bin_dir / "docker").write_text(
        f"""#!/bin/sh
echo "$*" >> {tmp_path}/docker.log
case "$1" in
  info) {"exit 0" if info_ok else "exit 1"};;
  ps) cat {tmp_path}/containers.tsv;;
  logs) i=$((61 - $3)); while [ "$i" -le 60 ]; do echo "log line $i of $4"; i=$((i+1)); done;;
  inspect) cat {tmp_path}/health-$4.json 2>/dev/null || echo null;;
esac
exit 0
"""
    )
    (bin_dir / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    return tmp_path / "docker.log"


UNHEALTHY = "work-postgres-1\tUp 40 seconds (unhealthy)\nwork-cache-1\tUp 40 seconds (healthy)\nwork-old-1\tExited (1) 3 seconds ago\n"


async def test_a_failed_check_shows_the_containers_that_are_not_healthy_and_what_they_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)

    [_, check] = await ran("echo 'container work-postgres-1 is unhealthy'; exit 1", tmp_path)

    assert isinstance(check, Check)
    assert check.code == 1
    assert check.output.startswith("container work-postgres-1 is unhealthy\n")
    assert "work-postgres-1" in check.output.split("the step's containers")[1]
    assert "log line 60 of work-postgres-1" in check.output
    assert "log line 21 of work-postgres-1" in check.output
    assert "log line 20 of work-postgres-1" not in check.output, "only the last 40 lines"
    assert "log line 60 of work-old-1" in check.output
    assert "log line 60 of work-cache-1" not in check.output, "a healthy container is not logged"


async def test_a_check_that_passes_asks_docker_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)

    [_, check] = await ran("echo fine", tmp_path)

    assert check == Check(0, "fine\n")
    assert not log.exists()


async def test_with_a_daemon_that_is_not_there_the_output_is_the_commands_alone(tmp_path: Path) -> None:
    [_, check] = await ran("echo bad; exit 2", tmp_path)

    assert check == Check(2, "bad\n")


async def test_a_daemon_that_does_not_answer_adds_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY, info_ok=False)

    [_, check] = await ran("echo bad; exit 2", tmp_path)

    assert check == Check(2, "bad\n")
    assert "ps" not in log.read_text()


async def test_no_containers_adds_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_docker(tmp_path, monkeypatch, containers="")

    [_, check] = await ran("echo bad; exit 2", tmp_path)

    assert check == Check(2, "bad\n")


async def test_a_daemon_that_hangs_does_not_hang_the_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text("#!/bin/sh\nsleep 30\n")
    (bin_dir / "docker").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    events: list[Event] = []

    await run_check("echo bad; exit 2", tmp_path, events.append, docker_timeout=0.3)

    assert events[-1] == Check(2, "bad\n")


async def test_the_containers_are_still_there_when_the_output_is_long(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)

    [_, check] = await ran("yes x | head -c 200000; exit 1", tmp_path)

    assert isinstance(check, Check)
    assert len(check.output) <= KEPT
    assert check.output.endswith("log line 60 of work-old-1\n")


PULL = """ dad2840f1c78 Extracting [=>   ]  10MB/121.4MB
 dad2840f1c78 Extracting [==>  ]  20MB/121.4MB
 dad2840f1c78 Extracting [===> ]  30MB/121.4MB
 dad2840f1c78 Pull complete
 1837bb99b431 Extracting [=====]  19.43kB/19.43kB
 1837bb99b431 Extracting [=====]  19.43kB/19.43kB
 1837bb99b431 Pull complete
 postgres Pulled
"""


def test_the_progress_of_a_layer_shows_once_at_its_last_line() -> None:
    assert collapse_progress(PULL) == (
        " dad2840f1c78 Extracting [===> ]  30MB/121.4MB\n"
        " dad2840f1c78 Pull complete\n"
        " 1837bb99b431 Extracting [=====]  19.43kB/19.43kB\n"
        " 1837bb99b431 Pull complete\n"
        " postgres Pulled\n"
    )


def test_lines_that_are_not_pull_progress_are_never_touched() -> None:
    text = "[INFO] Downloading from central: https://x/a.pom\n[INFO] Downloading from central: https://x/b.pom\nBUILD\n"
    assert collapse_progress(text) == text


def test_two_layers_that_alternate_are_both_kept() -> None:
    text = " aaaaaaaaaaaa Downloading [=]  1MB/9MB\n bbbbbbbbbbbb Downloading [=]  1MB/9MB\n aaaaaaaaaaaa Downloading [==]  2MB/9MB\n"
    assert collapse_progress(text) == text


def test_a_text_with_no_final_newline_keeps_that() -> None:
    assert collapse_progress(" dad2840f1c78 Extracting [=]  1MB/2MB\n dad2840f1c78 Extracting [==]  2MB/2MB") == (
        " dad2840f1c78 Extracting [==]  2MB/2MB"
    )


async def test_a_command_that_prints_a_pulls_progress_has_it_collapsed_in_what_is_reported(tmp_path: Path) -> None:
    command = (
        "printf ' dad2840f1c78 Extracting [=]  1MB/2MB\\n dad2840f1c78 Extracting [==]  2MB/2MB\\nrest\\n'; exit 1"
    )

    [_, check] = await ran(command, tmp_path)

    assert check == Check(1, " dad2840f1c78 Extracting [==]  2MB/2MB\nrest\n")


HEALTH = (
    '{"Status":"unhealthy","FailingStreak":3,"Log":['
    '{"ExitCode":1,"Output":"/var/run/postgresql:5432 - no response\\n","End":"2026-11-21T21:10:31Z"},'
    '{"ExitCode":-1,"Output":"OCI runtime exec failed: setns\\n","End":"2026-11-21T21:10:36Z"}]}'
)


async def test_an_unhealthy_container_shows_the_last_probes_of_its_healthcheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)
    (tmp_path / "health-work-postgres-1.json").write_text(HEALTH)

    [_, check] = await ran("echo 'container work-postgres-1 is unhealthy'; exit 1", tmp_path)

    assert isinstance(check, Check)
    section = check.output.split("--- work-postgres-1")[1]
    assert "healthcheck" in section
    assert "exit code 1" in section
    assert "no response" in section
    assert "exit code -1" in section
    assert "OCI runtime exec failed: setns" in section


async def test_a_container_with_no_healthcheck_shows_no_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)

    [_, check] = await ran("echo bad; exit 1", tmp_path)

    assert isinstance(check, Check)
    assert "healthcheck" not in check.output


async def test_health_that_is_not_json_is_left_out_and_the_rest_of_the_report_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)
    (tmp_path / "health-work-postgres-1.json").write_text("not json at all")

    [_, check] = await ran("echo bad; exit 1", tmp_path)

    assert isinstance(check, Check)
    assert "log line 60 of work-postgres-1" in check.output
    assert "healthcheck" not in check.output


async def test_only_the_last_probes_are_shown_and_each_is_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_docker(tmp_path, monkeypatch, containers=UNHEALTHY)
    probes = ",".join(f'{{"ExitCode":1,"Output":"probe {n} {"x" * 900}","End":"t"}}' for n in range(1, 9))
    (tmp_path / "health-work-postgres-1.json").write_text('{"Status":"unhealthy","Log":[' + probes + "]}")

    [_, check] = await ran("echo bad; exit 1", tmp_path)

    assert isinstance(check, Check)
    assert "probe 8 " in check.output
    assert "probe 4 " not in check.output, "only the last probes"
    assert "x" * 600 not in check.output, "each probe is cut"
