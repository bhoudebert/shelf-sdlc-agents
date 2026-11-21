"""``scripts/shelf-step-docker``: the command of a step that has a Docker daemon of its own, with fake programs."""

import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WRAPPER = ROOT / "scripts" / "shelf-step-docker"

FAKES = {
    # The daemon answers `docker info` only after it has written everything it will write, so the wrapper never runs ahead of the
    # fake and a test never reads the files of a daemon that is still starting.
    "dockerd": (
        'echo "dockerd $*" >> "$FAKE/calls"; '
        'echo "resolv: $(cat "$SHELF_RESOLV_CONF" 2>/dev/null | tr "\\n" " ")" >> "$FAKE/calls"; '
        'echo "daemon noise on stdout"; echo "daemon log line" >&2; touch "$FAKE/started"; sleep 3'
    ),
    "docker": '[ -f "$FAKE/ready" ] && [ -f "$FAKE/started" ]',
    "setpriv": 'echo "setpriv $*"',
    "mount": (
        'echo "mount $*" >> "$FAKE/calls"; '
        '[ "$1" = --bind ] && { [ -n "$FAKE_BIND_FAILS" ] && exit 1; cp "$2" "$3"; }; exit 0'
    ),
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
        "SHELF_RESOLV_NEW": str(fake / "new-resolv.conf"),
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
    assert (
        done.stdout.strip()
        == "setpriv --reuid=1000 --regid=1000 --init-groups --no-new-privs shelf-check /run/shelf/task.json"
    )
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


def test_the_image_that_uses_it_carries_the_docker_projects_own_release_and_not_the_distributions() -> None:
    """Debian's docker.io is 26.1 with an older runc, whose exec could not enter a container on the guest's kernel."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    stage = dockerfile.split("FROM step AS step-docker")[1].split("\nFROM ")[0]
    copied = " ".join(stage.replace("\\\n", " ").split())
    for program in ("dockerd", "docker", "runc", "containerd", "docker-init", "docker-proxy"):
        assert re.search(rf"COPY --from=docker:\d+\.\d+\.\d+-dind [^\n]*/usr/local/bin/{program}\b", copied), program
    assert "/usr/local/libexec/docker/cli-plugins/docker-compose" in copied, "compose"
    assert not re.search(r"apt-get install[^\n]*\bdocker\.io\b", copied)
    assert not re.search(r"apt-get install[^\n]*\bdocker-cli\b", copied)
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


def read_only(path: Path) -> None:
    """What a guest's resolv.conf can be: a file nobody may write (the test never runs as root)."""
    path.chmod(0o444)


def test_a_resolv_conf_that_cannot_be_written_is_replaced_by_a_mount_and_the_step_still_runs(fake: Path) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")
    read_only(resolv(fake))

    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="213.186.33.99")

    assert done.returncode == 0, done.stderr
    assert "setpriv" in done.stdout
    assert f"mount --bind {fake / 'new-resolv.conf'} {resolv(fake)}" in (fake / "calls").read_text()
    assert (fake / "new-resolv.conf").read_text() == "nameserver 213.186.33.99\n"


def test_when_the_mount_is_refused_a_writable_resolv_conf_is_written_directly(fake: Path) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")

    done = run(
        fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="213.186.33.99", FAKE_BIND_FAILS="1"
    )

    assert done.returncode == 0, done.stderr
    assert resolv(fake).read_text() == "nameserver 213.186.33.99\n"


def test_when_nothing_can_set_the_resolvers_the_step_still_runs_and_the_reason_is_said(fake: Path) -> None:
    resolv(fake).write_text("nameserver 127.0.0.11\n")
    read_only(resolv(fake))

    done = run(
        fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="213.186.33.99", FAKE_BIND_FAILS="1"
    )

    assert done.returncode == 0, done.stderr
    assert "setpriv" in done.stdout
    assert "could not set the resolvers" in done.stderr
    assert resolv(fake).read_text() == "nameserver 127.0.0.11\n"


def test_a_missing_resolv_conf_does_not_stop_the_step(fake: Path) -> None:
    done = run(
        fake, "shelf-step", "/run/shelf/task.json", ready=True, SHELF_STEP_DNS="213.186.33.99", FAKE_BIND_FAILS="1"
    )

    assert done.returncode == 0, done.stderr
    assert "setpriv" in done.stdout


def test_the_steps_own_command_keeps_no_new_privileges_although_the_daemons_container_does_not(fake: Path) -> None:
    done = run(fake, "shelf-step", "/run/shelf/task.json", ready=True)

    assert "--no-new-privs" in done.stdout
