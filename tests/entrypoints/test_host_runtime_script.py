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
  network) ;;
  run)
    case "$*" in
      *"grep '^nameserver'"*) grep '^nameserver' "$state/upstream";;
      *nslookup*)
        if [ -f "$state/dns_works" ]; then echo "Name: api.anthropic.com"; else echo ";; connection timed out"; fi;;
      *"uname -r"*) cat "$state/guest";;
      *--entrypoint*)
        works=$(cat "$state/works" 2>/dev/null || echo standard)
        level=1
        case "$*" in *seccomp=unconfined*) level=2;; esac
        case "$*" in *systempaths=unconfined*) level=3;; esac
        case "$*" in *--cgroupns=host*) level=4;; esac
        need=99
        case "$works" in standard) need=1;; unconfined) need=2;; systempaths) need=3;; full) need=4;; esac
        if [ "$level" -ge "$need" ]; then printf 'cgroup-rw\\ninner-ok\\n'; else
          echo "mkdir: can't create directory '/sys/fs/cgroup/init': Read-only file system"; fi;;
    esac;;
  rm) ;;
esac
exit 0
""",
    "ss": 'cat "$FAKE_STATE/listening" 2>/dev/null; exit 0',
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
    (state / "upstream").write_text("nameserver 213.186.33.99\nsearch openstacklocal\n")
    (state / "dns_works").write_text("")
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
    for flag in (
        "--runtime kata",
        "--cap-add SYS_ADMIN",
        "--cap-add NET_ADMIN",
        "--tmpfs /run:rw,nosuid,size=64m",
        "--tmpfs /var/lib/docker:rw,size=",
    ):
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
    assert not any("systempaths=unconfined" in p or "--cgroupns=host" in p for p in probes)


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
    (host.state / "works").write_text("full\n")

    done = host.run("--probe")

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip().splitlines()[-1] == "profile=full"


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


def body_user(rules: object, ask: object) -> str:
    from shelf.domain.stepspec import container_spec  # noqa: PLC0415

    return str(container_spec(ask, rules, expires=1)["User"])  # pyright: ignore[reportArgumentType]


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
        # the rest of the runner's container, flag by flag
        assert host["ReadonlyRootfs"] is True
        assert "--read-only" in caps.group(1)
        assert host["Init"] is True
        assert "--init" in caps.group(1)
        assert body_user(rules, ask.value) == "0:0"
        assert "--user 0:0" in caps.group(1)
        assert host["Tmpfs"]["/tmp"].startswith("rw,nosuid,exec,size=")  # noqa: S108
        assert "--tmpfs /tmp:rw,nosuid,exec,size=" in caps.group(1)
        # the storage of the step's daemon is memory in the runner as in the proof (the size follows the step's limit there)
        assert host["Tmpfs"]["/var/lib/docker"].startswith("rw,size=")
        assert "--tmpfs /var/lib/docker:rw,size=" in caps.group(1)
        assert not [m for m in host["Mounts"] if m["Target"] == "/var/lib/docker"]
        wanted = [f"--security-opt {o}" for o in host["SecurityOpt"]]
        wanted += ["--cgroupns=host"] if host.get("CgroupnsMode") == "host" else []
        wanted += ["--cap-add ALL"] if "ALL" in host["CapAdd"] else []
        listed = re.search(rf'{profile}\) printf \'%s\' "([^"]*)"', script)
        assert listed is not None, profile
        assert listed.group(1) == " ".join(wanted), profile
    assert re.search(r'profiles="([^"]*)"', script).group(1).split() == list(DOCKER_PROFILES)  # pyright: ignore[reportOptionalMemberAccess]


def test_probing_prints_the_resolvers_it_proved_and_the_profile_stays_the_last_line(host: Host) -> None:
    ready_host(host)

    done = host.run("--probe")

    assert done.returncode == 0, done.stderr
    lines = done.stdout.strip().splitlines()
    assert lines[-2:] == ["dns=213.186.33.99", "profile=standard"]


def test_the_hosts_own_loopback_resolver_is_not_a_resolver_a_step_can_use(host: Host) -> None:
    ready_host(host)
    (host.state / "upstream").write_text("nameserver 127.0.0.53\nnameserver 213.186.33.99\nnameserver 8.8.8.8\n")

    done = host.run("--probe")

    assert "dns=213.186.33.99,8.8.8.8" in done.stdout


def test_a_host_with_only_a_loopback_resolver_fails_and_says_to_set_one(host: Host) -> None:
    ready_host(host)
    (host.state / "upstream").write_text("nameserver 127.0.0.53\n")

    done = host.run("--probe")

    assert done.returncode == 1
    assert "SHELF_STEP_DNS" in done.stderr
    assert "profile=" not in done.stdout


def test_resolvers_the_operator_set_are_proved_instead_of_the_hosts_own(host: Host) -> None:
    ready_host(host)

    done = host.run("--probe", SHELF_STEP_DNS="9.9.9.9")

    assert "dns=9.9.9.9" in done.stdout
    assert "grep '^nameserver'" not in docker_calls(host)


def test_resolvers_that_resolve_nothing_in_a_step_fail_the_probe(host: Host) -> None:
    ready_host(host)
    (host.state / "dns_works").unlink()

    done = host.run("--probe")

    assert done.returncode == 1
    assert "dns=" not in done.stdout
    assert "profile=" not in done.stdout
    assert re.search(r"api\.anthropic\.com", done.stderr)


def test_the_proof_runs_under_the_runtime_on_a_network_of_its_own_and_removes_it(host: Host) -> None:
    ready_host(host)

    host.run("--probe")

    calls = docker_calls(host).splitlines()
    proof = next(line for line in calls if "nslookup" in line)
    assert "--runtime kata" in proof
    assert "--network shelf-probe-" in proof
    assert any(line.startswith("network create shelf-probe-") for line in calls)
    assert any(line.startswith("network rm shelf-probe-") for line in calls)


def test_the_network_of_the_proof_is_removed_even_when_the_proof_fails(host: Host) -> None:
    ready_host(host)
    (host.state / "dns_works").unlink()

    host.run("--probe")

    assert any(line.startswith("network rm shelf-probe-") for line in docker_calls(host).splitlines())


def test_the_whole_run_also_proves_that_a_step_resolves_names(host: Host) -> None:
    done = host.run("--yes")

    assert done.returncode == 0, done.stderr
    assert "a step resolves names with 213.186.33.99" in done.stdout


def test_the_whole_run_fails_when_a_step_cannot_resolve_names(host: Host) -> None:
    (host.state / "dns_works").unlink()

    done = host.run("--yes")

    assert done.returncode == 1
    assert "Ready." not in done.stdout


def test_only_nameserver_lines_are_taken_whatever_else_the_file_holds(host: Host) -> None:
    ready_host(host)
    shell = host.bin / "docker"
    original = shell.read_text()
    # a container whose grep let other lines through: the script must not trust it to filter
    shell.write_text(original.replace('''grep '^nameserver' "$state/upstream"''', '''cat "$state/upstream"'''))

    done = host.run("--probe")

    assert "dns=213.186.33.99\n" in done.stdout
    assert "openstacklocal" not in done.stdout


def proof_script() -> str:
    """The script the proof runs inside the step: what the guest is asked to do, not what the fake pretends."""
    text = SCRIPT.read_text()
    return text[text.index("probe_body='") : text.index("# A port of this host that is already in use")]


def test_the_proof_in_the_step_runs_a_container_with_a_healthcheck_and_waits_for_it_to_be_healthy() -> None:
    body = proof_script()
    assert "--health-cmd" in body
    assert "State.Health.Status" in body
    assert "healthy" in body


def test_the_proof_in_the_step_executes_a_command_in_a_running_container() -> None:
    assert "docker exec" in proof_script()


def test_the_proof_in_the_step_publishes_a_port_and_asks_it_from_inside() -> None:
    body = proof_script()
    assert "-p " in body
    assert "wget" in body


def test_the_proof_only_says_ok_after_every_part_of_it_worked() -> None:
    body = proof_script()
    last = body.rstrip().splitlines()[-1]
    assert "inner-ok" in last
    for failure in ("exec-failed", "service-did-not-start", "publish-failed"):
        assert body.index(failure) < body.index("inner-ok")


def test_the_port_the_proof_publishes_is_one_the_host_already_uses(host: Host) -> None:
    ready_host(host)
    (host.state / "listening").write_text(
        "LISTEN 0 128 127.0.0.1:631 0.0.0.0:*\nLISTEN 0 4096 0.0.0.0:5432 0.0.0.0:*\nLISTEN 0 4096 [::]:8080 [::]:*\n"
    )

    host.run("--probe")

    call = next(line for line in docker_calls(host).splitlines() if "--entrypoint" in line)
    assert "PORT=5432" in call


def test_with_nothing_listening_the_proof_publishes_a_common_port(host: Host) -> None:
    ready_host(host)

    host.run("--probe")

    call = next(line for line in docker_calls(host).splitlines() if "--entrypoint" in line)
    assert "PORT=8080" in call


def test_the_proof_in_the_step_is_valid_shell() -> None:
    """The guest runs it and nothing here can: a quoting slip would only show on a real host."""
    body = proof_script().split("probe_body='", 1)[1].rsplit("'\n", 1)[0].replace("'\"'\"'", "'")

    checked = subprocess.run(["sh", "-n"], input=body, capture_output=True, text=True, check=False)  # noqa: S607

    assert checked.returncode == 0, checked.stderr


def test_the_script_itself_is_valid_shell() -> None:
    checked = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)  # noqa: S603, S607

    assert checked.returncode == 0, checked.stderr


def test_the_proof_runs_in_the_image_the_runner_uses_when_it_is_built(host: Host) -> None:
    ready_host(host)

    host.run("--probe")

    call = next(line for line in docker_calls(host).splitlines() if "--entrypoint" in line)
    assert "shelf-sdlc-step-docker:local" in call
    assert "docker:28-dind" not in call


def test_when_the_step_image_is_not_built_the_proof_says_it_fell_back_and_is_weaker(host: Host) -> None:
    ready_host(host)
    shell = host.bin / "docker"
    shell.write_text(shell.read_text().replace("  image) exit 0;;", "  image) exit 1;;"))

    done = host.run("--probe")

    call = next(line for line in docker_calls(host).splitlines() if "--entrypoint" in line)
    assert "docker:28-dind" in call
    assert "not built" in done.stderr + done.stdout
    assert "weaker" in done.stderr + done.stdout


def test_a_published_port_is_asked_from_a_container_on_the_steps_own_network() -> None:
    """The step image has no wget: a busybox container on the host network of the step asks it."""
    body = proof_script()
    assert "--network host" in body
    assert "busybox wget" in body


def test_the_proof_starts_a_service_that_drops_its_privileges_and_waits_for_its_own_healthcheck() -> None:
    """A root busybox can be entered without CAP_SYS_PTRACE; a database that changed user cannot: so the proof uses one."""
    body = proof_script()
    assert "POSTGRES_PASSWORD" in body
    assert "pg_isready" in body
    assert "--health-cmd" in body
    assert "db-never-healthy" in body
    assert body.index("db-never-healthy") < body.index("inner-ok")
    assert "DB_IMAGE=${SHELF_PROBE_DB_IMAGE:-postgres:" in SCRIPT.read_text()
    waits = r'until \[ "\$\(docker inspect -f "\{\{\.State\.Health\.Status\}\}" db '
    assert re.search(waits, body), "the proof waits for the database to become healthy"


def test_the_proof_asks_the_published_port_of_the_database_too() -> None:
    body = proof_script()
    assert "nc -z" in body or "busybox wget" in body


def test_dns_proves_the_resolvers_alone_and_changes_nothing(host: Host) -> None:
    ready_host(host)

    done = host.run("--dns", SHELF_STEP_DNS="9.9.9.9")

    assert done.returncode == 0, done.stderr
    assert "dns=9.9.9.9" in done.stdout
    assert "profile=" not in done.stdout
    calls = docker_calls(host)
    assert "nslookup" in calls
    assert "--cap-add" not in calls, "the profile is not probed"


def test_dns_fails_with_what_the_step_said_when_the_resolvers_do_not_resolve(host: Host) -> None:
    ready_host(host)
    (host.state / "dns_works").unlink()

    done = host.run("--dns", SHELF_STEP_DNS="9.9.9.9")

    assert done.returncode == 1
    assert "dns=" not in done.stdout
    assert re.search(r"api\.anthropic\.com", done.stderr)


def test_dns_without_resolvers_to_prove_says_so_and_fails(host: Host) -> None:
    ready_host(host)

    done = host.run("--dns")

    assert done.returncode == 1
    assert "SHELF_STEP_DNS" in done.stderr
