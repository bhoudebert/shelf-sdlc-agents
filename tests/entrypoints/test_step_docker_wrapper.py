"""``scripts/shelf-step-docker``: the command of a step that has a Docker daemon of its own, with fake programs."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WRAPPER = ROOT / "scripts" / "shelf-step-docker"

FAKES = {
    "dockerd": (
        'echo "dockerd $*" >> "$FAKE/calls"; '
        'echo "resolv: $(cat "$SHELF_RESOLV_CONF" 2>/dev/null | tr "\\n" " ")" >> "$FAKE/calls"; '
        'echo "daemon noise on stdout"; echo "daemon log line" >&2; sleep 3'
    ),
    "docker": '[ -f "$FAKE/ready" ]',
    "setpriv": 'echo "setpriv $*"',
    "mount": 'echo "mount $*" >> "$FAKE/calls"',
}


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    return tmp_path


def run(fake: Path, *args: str, ready: bool, **extra: str) -> subprocess.CompletedProcess[str]:
    if ready:
        (fake / "ready").write_text("")
    env = {
        **os.environ,
        "SHELF_RESOLV_CONF": str(fake / "resolv.conf"),
        **extra,
        "PATH": f"{fake / 'bin'}:{os.environ['PATH']}",
        "FAKE": str(fake),
        "SHELF_DOCKERD_LOG": str(fake / "dockerd.log"),
        "SHELF_DOCKERD_WAIT": "2",
    }
    return subprocess.run(  # noqa: S603
        ["sh", str(WRAPPER), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )


def test_it_starts_the_daemon_for_the_steps_group_and_then_runs_the_program_it_was_given_as_the_steps_user(
    fake: Path,
) -> None:
    done = run(fake, "shelf-check", "/run/shelf/task.json", ready=True)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "setpriv --reuid=1000 --regid=1000 --init-groups shelf-check /run/shelf/task.json"
    assert "dockerd --host=unix:///var/run/docker.sock --group=shelf" in (fake / "calls").read_text()


def test_what_the_daemon_prints_never_reaches_the_steps_output(fake: Path) -> None:
    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True)

    assert "daemon noise" not in done.stdout
    assert "daemon noise" in (fake / "dockerd.log").read_text()


def test_a_daemon_that_does_not_answer_ends_the_step_with_what_the_daemon_said(fake: Path) -> None:
    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=False)

    assert done.returncode == 1
    assert "did not start" in done.stderr
    assert "daemon log line" in done.stderr
    assert "setpriv" not in done.stdout


def test_the_image_that_uses_it_installs_the_daemon_the_client_and_compose() -> None:
    """Debian's docker.io holds the daemon only: without docker-cli the wrapper waits for a client that is not there."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    stage = dockerfile.split("FROM step AS step-docker")[1].split("\nFROM ")[0]
    for package in ("docker.io", "docker-cli", "docker-compose"):
        assert re.search(rf"\b{re.escape(package)}\b", stage), package
    assert "COPY scripts/shelf-step-docker /usr/local/bin/shelf-step-docker" in stage
    assert 'CMD ["shelf-step-docker"' in stage


def test_the_cgroup_filesystem_and_the_system_paths_are_made_writable_before_the_daemon_starts(fake: Path) -> None:
    run(fake, "shelf-step", "/run/shelf/task.json", ready=True)

    calls = (fake / "calls").read_text().splitlines()
    assert calls[0] == "mount -o remount,rw /sys/fs/cgroup"
    assert calls[1] == "mount -o remount,bind,rw /proc/sys"
    assert calls[2].startswith("dockerd ")


def test_a_remount_that_is_refused_does_not_stop_the_step_from_trying_the_daemon(fake: Path) -> None:
    (fake / "bin" / "mount").write_text('#!/bin/sh\necho "mount $*" >> "$FAKE/calls"\nexit 1\n')

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True)

    assert done.returncode == 0, done.stderr
    assert "setpriv" in done.stdout


def test_a_bind_remount_of_the_system_paths_that_is_refused_is_tried_the_plain_way(fake: Path) -> None:
    (fake / "bin" / "mount").write_text(
        '#!/bin/sh\necho "mount $*" >> "$FAKE/calls"\n[ "$2" = remount,bind,rw ] && exit 1\nexit 0\n'
    )

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True)

    assert done.returncode == 0, done.stderr
    assert "mount -o remount,rw /proc/sys" in (fake / "calls").read_text()


def resolv(fake: Path) -> Path:
    return fake / "resolv.conf"


def test_the_operators_resolvers_are_written_before_the_daemon_starts(fake: Path) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="213.186.33.99,8.8.8.8")

    assert done.returncode == 0, done.stderr
    assert resolv(fake).read_text() == "nameserver 213.186.33.99\nnameserver 8.8.8.8\n"
    assert "resolv: nameserver 213.186.33.99 nameserver 8.8.8.8" in (fake / "calls").read_text()


def test_an_ipv6_resolver_is_written_too(fake: Path) -> None:
    run(fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="2606:4700:4700::1111")

    assert resolv(fake).read_text() == "nameserver 2606:4700:4700::1111\n"


@pytest.mark.parametrize("value", [None, ""])
def test_with_no_resolvers_the_file_docker_wrote_stays(fake: Path, value: str | None) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")
    extra = {} if value is None else {"SHELF_STEP_DNS": value}

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True, **extra)

    assert done.returncode == 0, done.stderr
    assert resolv(fake).read_text() == "nameserver 127.0.0.11\n"


@pytest.mark.parametrize("value", ["example.org", "1.1.1.1;touch pwned", "1.1.1.1 8.8.8.8", "$(id)"])
def test_something_that_is_not_an_address_is_never_written_and_the_step_goes_on(fake: Path, value: str) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS=value)

    assert done.returncode == 0, done.stderr
    assert resolv(fake).read_text() == "nameserver 127.0.0.11\n"
    assert "SHELF_STEP_DNS" in done.stderr
    assert "setpriv" in done.stdout
