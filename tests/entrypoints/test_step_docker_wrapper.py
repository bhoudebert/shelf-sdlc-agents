"""``scripts/shelf-step-docker``: the command of a step that has a Docker daemon of its own, with fake programs."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WRAPPER = ROOT / "scripts" / "shelf-step-docker"

FAKES = {
    "dockerd": 'echo "dockerd $*" >> "$FAKE/calls"; echo "daemon noise on stdout"; echo "daemon log line" >&2; sleep 3',
    "docker": '[ -f "$FAKE/ready" ]',
    "setpriv": 'echo "setpriv $*"',
}


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    return tmp_path


def run(fake: Path, *args: str, ready: bool) -> subprocess.CompletedProcess[str]:
    if ready:
        (fake / "ready").write_text("")
    env = {
        **os.environ,
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


def test_it_starts_the_daemon_for_the_steps_group_and_then_runs_the_step_as_its_user(fake: Path) -> None:
    done = run(fake, "/run/shelf/task.json", ready=True)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "setpriv --reuid=1000 --regid=1000 --init-groups shelf-step /run/shelf/task.json"
    assert "dockerd --host=unix:///var/run/docker.sock --group=shelf" in (fake / "calls").read_text()


def test_what_the_daemon_prints_never_reaches_the_steps_output(fake: Path) -> None:
    done = run(fake, "/run/shelf/task.json", ready=True)

    assert "daemon noise" not in done.stdout
    assert "daemon noise" in (fake / "dockerd.log").read_text()


def test_a_daemon_that_does_not_answer_ends_the_step_with_what_the_daemon_said(fake: Path) -> None:
    done = run(fake, "/run/shelf/task.json", ready=False)

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
