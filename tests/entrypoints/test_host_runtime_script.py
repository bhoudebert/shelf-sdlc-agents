"""``deploy/host-runtime.sh`` against a fake host: every program it calls is a small script, and every path of the host sits
under one folder (``SHELF_HOST_ROOT``), so nothing here touches the machine that runs the tests."""

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "deploy" / "host-runtime.sh"
PINNED = {m[0]: m[1] for m in re.findall(r'KATA_SHA256_(\w+)="(\w+)"', SCRIPT.read_text())}["amd64"]
HOST_KERNEL = "6.14.0-host"
GUEST_KERNEL = "6.12.0-kata"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="the script needs jq")

FAKES = {
    "uname": 'case "$1" in -m) echo x86_64;; -r) echo "$HOST_KERNEL";; esac',
    "id": 'echo "${FAKE_UID:-0}"',
    "docker": """
state="$FAKE_STATE"
echo "$*" >> "$state/docker.log"
case "$1" in
  version) echo 28.2.2;;
  info)
    case "$*" in
      *Runtimes*) cat "$state/runtimes" 2>/dev/null | tr '\\n' ' ';;
      *LiveRestore*) cat "$state/live" 2>/dev/null || echo false;;
    esac;;
  ps)
    case "$*" in
      *--format*) cat "$state/names" 2>/dev/null;;
      *) cat "$state/ids" 2>/dev/null;;
    esac;;
  image) exit 0;;
  pull) exit 0;;
  run)
    case "$*" in
      *"uname -r"*) cat "$state/guest";;
      *--entrypoint*)
        works=$(cat "$state/works" 2>/dev/null || echo standard)
        level=1
        case "$*" in *seccomp=unconfined*) level=2;; esac
        case "$*" in *--cgroupns=host*) level=3;; esac
        need=99
        case "$works" in standard) need=1;; unconfined) need=2;; cgroupns) need=3;; esac
        if [ "$level" -ge "$need" ]; then printf 'cgroup-rw\\ninner-ok\\n'; else
          echo "mkdir: can't create directory '/sys/fs/cgroup/init': Read-only file system"; fi;;
    esac;;
  rm) ;;
esac
exit 0
""",
    "modprobe": 'mkdir -p "$SHELF_HOST_ROOT/sys/module/$1"',
    "systemctl": """
echo "$*" >> "$FAKE_STATE/systemctl.log"
case "$1" in
  reload) [ -f "$FAKE_STATE/reload_registers" ] || exit 0;;
  restart) ;;
  *) exit 0;;
esac
if grep -q '"kata"' "$SHELF_HOST_ROOT/etc/docker/daemon.json" 2>/dev/null; then echo kata >> "$FAKE_STATE/runtimes"; fi
""",
    "apt-get": 'echo "$*" >> "$FAKE_STATE/apt.log"',
    "curl": 'out=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && out="$2"; shift; done; cp "$FAKE_STATE/release.tar" "$out"',
    "sha256sum": 'echo "$FAKE_SHA  $1"',
    "zstd": 'cat "$2"',
}


@dataclass
class Host:
    root: Path
    state: Path
    bin: Path

    def run(self, *args: str, uid: int = 0, sha: str = PINNED, **extra: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "SHELF_HOST_ROOT": str(self.root),
            "FAKE_STATE": str(self.state),
            "FAKE_UID": str(uid),
            "FAKE_SHA": sha,
            "HOST_KERNEL": HOST_KERNEL,
            "TMPDIR": str(self.state),
            **extra,
        }
        return subprocess.run(  # noqa: S603
            ["sh", str(SCRIPT), *args],  # noqa: S607
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )

    @property
    def daemon_json(self) -> Path:
        return self.root / "etc/docker/daemon.json"

    def installed(self, version: str = "4.4.0") -> None:
        shim = self.root / "opt/kata/runtime-rs/bin/containerd-shim-kata-v2"
        shim.parent.mkdir(parents=True)
        shim.write_text("#!/bin/sh\n")
        shim.chmod(0o755)
        (self.root / "opt/kata/.shelf-release").write_text(f"{version}\n")


def release_archive() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, mode in (
            ("opt/kata/runtime-rs/bin/containerd-shim-kata-v2", 0o755),
            ("opt/kata/share/x.toml", 0o644),
        ):
            data = b"#!/bin/sh\n"
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), mode
            archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


@pytest.fixture
def host(tmp_path: Path) -> Host:
    """An Ubuntu host with KVM, Docker 28 and one container running, with nothing of Kata on it."""
    root, state, bin_dir = tmp_path / "root", tmp_path / "state", tmp_path / "bin"
    for folder in (root / "etc", root / "dev", state, bin_dir):
        folder.mkdir(parents=True)
    (root / "etc/os-release").write_text('ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 25.04"\n')
    (root / "dev/kvm").write_text("")
    (state / "runtimes").write_text("runc\n")
    (state / "ids").write_text("abc123\n")
    (state / "names").write_text("shelf-sdlc-web-1\n")
    (state / "guest").write_text(f"{GUEST_KERNEL}\n")
    (state / "reload_registers").write_text("")
    (state / "works").write_text("standard\n")
    (state / "release.tar").write_bytes(release_archive())
    for name, body in FAKES.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    return Host(root, state, bin_dir)


def test_a_host_with_every_step_done_is_ready_and_nothing_changes(host: Host) -> None:
    host.installed()
    (host.root / "sys/module/vhost_vsock").mkdir(parents=True)
    (host.root / "sys/module/vhost_net").mkdir(parents=True)
    (host.root / "etc/modules-load.d").mkdir()
    (host.root / "etc/modules-load.d/shelf-kata.conf").write_text("vhost_vsock\nvhost_net\n")
    host.daemon_json.parent.mkdir()
    host.daemon_json.write_text(
        json.dumps({"runtimes": {"kata": {"runtimeType": "/opt/kata/runtime-rs/bin/containerd-shim-kata-v2"}}})
    )
    (host.state / "runtimes").write_text("runc\nkata\n")
    before = host.daemon_json.read_text()

    done = host.run("--check")

    assert done.returncode == 0, done.stderr
    assert "[todo]" not in done.stdout
    assert "Ready." in done.stdout
    assert host.daemon_json.read_text() == before
    assert not (host.state / "apt.log").exists()


def test_looking_changes_nothing_and_names_what_is_missing(host: Host) -> None:
    done = host.run("--check")

    assert done.returncode == 2
    for what in ("kernel modules", "Kata Containers 4.4.0", "the runtime 'kata'", "Docker lists"):
        assert f"[todo] {what}" in done.stdout or what in done.stdout
    assert not (host.root / "opt").exists()
    assert not host.daemon_json.exists()
    assert not (host.root / "sys").exists()


def test_a_host_without_kvm_is_refused_before_anything_is_changed(host: Host) -> None:
    (host.root / "dev/kvm").unlink()

    done = host.run("--yes")

    assert done.returncode == 1
    assert "/dev/kvm" in done.stderr
    assert "isolated-step-environments" in done.stderr
    assert not (host.root / "opt").exists()


def test_a_system_that_is_not_ubuntu_or_debian_is_refused(host: Host) -> None:
    (host.root / "etc/os-release").write_text('ID=fedora\nPRETTY_NAME="Fedora Linux 43"\n')

    done = host.run("--yes")

    assert done.returncode == 1
    assert "Ubuntu and Debian" in done.stderr
    assert "Fedora" in done.stderr


def test_nobody_at_the_terminal_and_no_yes_changes_nothing(host: Host) -> None:
    done = host.run()

    assert done.returncode == 1
    assert "--yes" in done.stderr
    assert not (host.root / "opt").exists()
    assert not host.daemon_json.exists()


def test_a_user_who_is_not_root_is_told_to_use_sudo(host: Host) -> None:
    done = host.run("--yes", uid=1000)

    assert done.returncode == 1
    assert "sudo" in done.stderr


def test_the_whole_run_installs_registers_and_proves_a_daemon_in_a_step(host: Host) -> None:
    done = host.run("--yes")

    assert done.returncode == 0, done.stderr
    config = json.loads(host.daemon_json.read_text())
    assert config["runtimes"]["kata"]["runtimeType"] == "/opt/kata/runtime-rs/bin/containerd-shim-kata-v2"
    assert (host.root / "opt/kata/runtime-rs/bin/containerd-shim-kata-v2").exists()
    assert (host.root / "opt/kata/.shelf-release").read_text().strip() == "4.4.0"
    assert (host.root / "etc/modules-load.d/shelf-kata.conf").read_text().split() == ["vhost_vsock", "vhost_net"]
    assert not (host.root / "opt/.shelf-kata-stage").exists()
    assert "install: curl zstd" not in done.stdout  # fakes are on the path: nothing to install
    assert f"its own kernel ({GUEST_KERNEL}; the host runs {HOST_KERNEL})" in done.stdout
    assert "a Docker daemon inside a step runs a container (profile standard)" in done.stdout
    assert "reload docker" in (host.state / "systemctl.log").read_text()
    assert "restart" not in (host.state / "systemctl.log").read_text()


def test_it_says_what_it_will_change_before_changing_it(host: Host) -> None:
    (host.bin / "jq").write_text("#!/bin/sh\nexit 127\n")  # a jq the script cannot use: it must plan to install one
    (host.bin / "jq").chmod(0o755)
    nobody = host.run()

    assert "This will:" in nobody.stdout
    assert "download Kata 4.4.0" in nobody.stdout
    assert "a dated copy" in nobody.stdout


def test_running_it_again_changes_nothing_and_runs_the_checks(host: Host) -> None:
    assert host.run("--yes").returncode == 0
    daemon = host.daemon_json.read_text()
    backups = sorted(p.name for p in host.daemon_json.parent.iterdir())

    again = host.run("--yes")

    assert again.returncode == 0, again.stderr
    assert "[todo]" not in again.stdout
    assert "[do]" not in again.stdout
    assert host.daemon_json.read_text() == daemon
    assert sorted(p.name for p in host.daemon_json.parent.iterdir()) == backups
    assert "a Docker daemon inside a step runs a container (profile standard)" in again.stdout


def test_other_settings_in_the_daemon_file_are_kept_and_a_dated_copy_is_made(host: Host) -> None:
    host.daemon_json.parent.mkdir()
    host.daemon_json.write_text(json.dumps({"log-driver": "local", "runtimes": {"other": {"path": "/usr/bin/other"}}}))

    done = host.run("--yes")

    assert done.returncode == 0, done.stderr
    config = json.loads(host.daemon_json.read_text())
    assert config["log-driver"] == "local"
    assert config["runtimes"]["other"] == {"path": "/usr/bin/other"}
    assert "kata" in config["runtimes"]
    copies = [p for p in host.daemon_json.parent.iterdir() if p.name.startswith("daemon.json.shelf-")]
    assert len(copies) == 1
    assert json.loads(copies[0].read_text())["log-driver"] == "local"


def test_a_daemon_file_that_is_not_json_is_left_untouched(host: Host) -> None:
    host.daemon_json.parent.mkdir()
    host.daemon_json.write_text("{ not json")

    done = host.run("--yes")

    assert done.returncode == 1
    assert "not valid JSON" in done.stderr
    assert host.daemon_json.read_text() == "{ not json"


def test_a_download_that_does_not_match_the_checksum_is_never_unpacked(host: Host) -> None:
    done = host.run("--yes", sha=hashlib.sha256(b"something else").hexdigest())

    assert done.returncode == 1
    assert "checksum" in done.stderr
    assert not (host.root / "opt/kata").exists()
    assert not (host.root / "opt/.shelf-kata-stage").exists()


def test_a_failed_update_leaves_the_folder_of_the_old_release_as_it_was(host: Host) -> None:
    host.installed(version="4.3.0")

    done = host.run("--yes", sha="0" * 64)

    assert done.returncode == 1
    assert (host.root / "opt/kata/.shelf-release").read_text().strip() == "4.3.0"
    assert (host.root / "opt/kata/runtime-rs/bin/containerd-shim-kata-v2").exists()


def test_a_reload_that_does_not_register_the_runtime_lists_what_a_restart_would_stop(host: Host) -> None:
    (host.state / "reload_registers").unlink()

    done = host.run("--yes")

    assert done.returncode == 3
    assert "did not pick the runtime up" in done.stdout
    assert "shelf-sdlc-web-1" in done.stdout
    assert "restart" not in (host.state / "systemctl.log").read_text()


def test_a_restart_happens_only_when_it_is_asked_for(host: Host) -> None:
    (host.state / "reload_registers").unlink()
    # a restart reads the file again: the fake registers the runtime on "restart", not on "reload"
    (host.bin / "systemctl").write_text(
        FAKES_RESTART.replace("$STATE", str(host.state)).replace("$ROOT", str(host.root))
    )
    (host.bin / "systemctl").chmod(0o755)

    done = host.run("--yes", "--restart-docker")

    assert done.returncode == 0, done.stderr
    assert "restart docker" in (host.state / "systemctl.log").read_text()


FAKES_RESTART = """#!/bin/sh
echo "$*" >> "$STATE/systemctl.log"
[ "$1" = restart ] && grep -q '"kata"' "$ROOT/etc/docker/daemon.json" && echo kata >> "$STATE/runtimes"
exit 0
"""


def test_a_step_that_reports_the_hosts_own_kernel_is_not_called_isolated(host: Host) -> None:
    (host.state / "guest").write_text(f"{HOST_KERNEL}\n")

    done = host.run("--yes")

    assert done.returncode == 1
    assert "not in a virtual machine" in done.stderr


def test_another_runtime_is_only_looked_for_never_installed(host: Host) -> None:
    assert host.run("--check").returncode == 2  # kata is missing
    (host.state / "runtimes").write_text("runc\nrunsc\n")

    other = host.run("--check", SHELF_STEP_RUNTIME="runsc")

    assert other.returncode == 0
    assert "Docker lists the runtime 'runsc'" in other.stdout
    assert not (host.root / "opt").exists()


def docker_calls(host: Host) -> str:
    return (host.state / "docker.log").read_text()


def test_the_proof_of_a_daemon_never_uses_privileged_mode(host: Host) -> None:
    assert host.run("--yes").returncode == 0
    assert "--privileged" not in docker_calls(host)


def test_the_proof_gives_the_container_what_the_runner_gives_a_step(host: Host) -> None:
    host.run("--yes")
    call = next(line for line in docker_calls(host).splitlines() if "--entrypoint" in line)
    for flag in ("--runtime kata", "--cap-add SYS_ADMIN", "--cap-add NET_ADMIN", "--tmpfs /run:rw,nosuid,size=64m"):
        assert flag in call


def test_a_host_that_needs_a_more_permissive_profile_is_told_which_and_how(host: Host) -> None:
    (host.state / "works").write_text("unconfined\n")

    done = host.run("--yes")

    assert done.returncode == 0, done.stderr
    assert "profile unconfined" in done.stdout
    assert "SHELF_STEP_DOCKER_PROFILE=unconfined" in done.stdout
    assert "a Docker daemon inside a step runs a container (profile standard)" not in done.stdout


def test_the_ladder_goes_up_one_profile_at_a_time_and_stops_at_the_first_that_works(host: Host) -> None:
    (host.state / "works").write_text("unconfined\n")
    host.run("--yes")
    probes = [line for line in docker_calls(host).splitlines() if "--entrypoint" in line]
    assert len(probes) == 2
    assert "seccomp=unconfined" not in probes[0]
    assert "seccomp=unconfined" in probes[1]
    assert not any("--cgroupns=host" in p for p in probes)


def test_a_host_where_no_profile_works_fails_and_shows_what_each_attempt_said(host: Host) -> None:
    (host.state / "works").write_text("none\n")

    done = host.run("--yes")

    assert done.returncode == 1
    assert "Read-only file system" in done.stdout + done.stderr
    assert "cannot be used on this host" in done.stdout + done.stderr


def ready_host(host: Host) -> None:
    assert host.run("--yes").returncode == 0
    (host.state / "docker.log").unlink()


def test_probing_names_the_first_profile_that_works_on_the_last_line(host: Host) -> None:
    ready_host(host)
    (host.state / "works").write_text("cgroupns\n")

    done = host.run("--probe")

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines()[-1] == "profile=cgroupns"


def test_probing_a_host_where_nothing_works_prints_no_profile_and_fails(host: Host) -> None:
    ready_host(host)
    (host.state / "works").write_text("none\n")

    done = host.run("--probe")

    assert done.returncode == 1
    assert "profile=" not in done.stdout


def test_probing_changes_nothing_on_the_host(host: Host) -> None:
    ready_host(host)
    daemon, systemctl = host.daemon_json.read_text(), (host.state / "systemctl.log").read_text()

    host.run("--probe")

    assert host.daemon_json.read_text() == daemon
    assert (host.state / "systemctl.log").read_text() == systemctl
    assert not any(line.startswith(("pull", "restart", "kill")) for line in docker_calls(host).splitlines())


def test_probing_before_the_runtime_is_there_says_to_install_it_first(host: Host) -> None:
    done = host.run("--probe")

    assert done.returncode == 2
    assert "profile=" not in done.stdout
    assert "host-runtime.sh" in done.stdout + done.stderr


def test_the_proof_runs_exactly_what_the_runner_would_start() -> None:
    """The script cannot import the runner's rules: this keeps its flags equal to them, so a proof is a proof."""
    from shelf.domain.result import Ok  # noqa: PLC0415
    from shelf.domain.stepspec import DOCKER_CAPS, DOCKER_PROFILES, RunnerRules, container_spec, parse_request  # noqa: PLC0415

    script = SCRIPT.read_text()
    caps = re.search(r'step_flags="([^"]*)"', script)
    assert caps is not None
    assert tuple(re.findall(r"--cap-add (\w+)", caps.group(1))) == DOCKER_CAPS

    for profile in DOCKER_PROFILES:
        rules = RunnerRules(image="i", docker_image="d", docker_runtime="kata", docker_profile=profile)
        body: dict[str, object] = {"key": "k", "repo": "a/b", "clone": "steps/x/repo", "docker": True, "input": {}}
        ask = parse_request(body, rules)
        assert isinstance(ask, Ok)
        host = container_spec(ask.value, rules, expires=1)["HostConfig"]
        assert f"--tmpfs /run:{host['Tmpfs']['/run']}" in (caps.group(1))
        wanted = [f"--security-opt {o}" for o in host["SecurityOpt"] if o != "no-new-privileges"]
        wanted += ["--cgroupns=host"] if host.get("CgroupnsMode") == "host" else []
        listed = re.search(rf'{profile}\) printf \'%s\' "([^"]*)"', script)
        assert listed is not None, profile
        assert listed.group(1) == " ".join(wanted), profile
    assert re.search(r'profiles="([^"]*)"', script).group(1).split() == list(DOCKER_PROFILES)  # pyright: ignore[reportOptionalMemberAccess]
