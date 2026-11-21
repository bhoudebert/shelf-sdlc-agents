import json
import os
import pty
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from shelf.entrypoints.runner import read_settings
from shelf.entrypoints.settings import from_environ

DEPLOY = Path(__file__).parents[2] / "deploy"


@pytest.fixture
def server(tmp_path: Path) -> Path:
    """A copy of deploy/ next to fake ``docker`` and ``ss`` programs, so the script runs without building anything."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "docker": (
            'echo "$@" >> "${DOCKER_LOG:-/dev/null}"; '
            'case "$*" in *" config -q"*) [ -z "$COMPOSE_ERROR" ] || { echo "$COMPOSE_ERROR" >&2; exit 1; };; esac; exit 0'
        ),
        "ss": 'cat "$SS_OUTPUT" 2>/dev/null; exit 0',
        "curl": 'echo \'{"status": "ok", "revision": "unknown"}\'',
        "git": "exit 1",
    }.items():
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_dir / name).chmod(0o755)
    return tmp_path


def write_env(server: Path, **values: str) -> None:
    base = {"PUBLIC_URL": "https://shelf.example.org", "SESSION_SECRET": "s3cret", "WEB_PORT": "8080", **values}
    (server / "deploy" / ".env").write_text("".join(f"{k}={v}\n" for k, v in base.items()))


def run(server: Path, busy: str = "", compose_error: str = "") -> subprocess.CompletedProcess[str]:
    (server / "ss.out").write_text(busy)
    env = {
        **os.environ,
        "COMPOSE_ERROR": compose_error,
        "PATH": f"{server / 'bin'}:{os.environ['PATH']}",
        "SS_OUTPUT": str(server / "ss.out"),
        "DOCKER_LOG": str(server / "docker.log"),
    }
    return subprocess.run(  # noqa: S603
        ["sh", str(server / "deploy" / "install.sh")],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


def test_an_empty_public_address_stops_the_script_before_anything_is_built(server: Path) -> None:
    write_env(server, PUBLIC_URL="")
    done = run(server)
    assert done.returncode == 1
    assert "PUBLIC_URL is empty" in done.stderr
    assert "Building revision" not in done.stdout


def test_an_empty_session_secret_stops_the_script(server: Path) -> None:
    write_env(server, SESSION_SECRET="")
    assert "SESSION_SECRET is empty" in run(server).stderr


def test_a_port_in_use_by_something_else_stops_the_script_and_says_what_the_port_is(server: Path) -> None:
    write_env(server)
    done = run(server, busy="LISTEN 0 4096 0.0.0.0:8080\n")
    assert done.returncode == 1
    assert "port 8080 is already in use" in done.stderr
    assert "not your site's public port" in done.stderr
    assert "Building revision" not in done.stdout


def test_a_compose_file_that_cannot_be_read_is_reported_as_such_and_not_as_a_busy_port(server: Path) -> None:
    write_env(server)
    done = run(server, busy="LISTEN 0 4096 0.0.0.0:8080\n", compose_error="failed to parse compose.container.yml")
    assert done.returncode == 1
    assert "cannot read the deployment files" in done.stderr
    assert "failed to parse compose.container.yml" in done.stderr
    assert "already in use" not in done.stderr
    assert "Building revision" not in done.stdout


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to read the files")
@pytest.mark.parametrize("overlays", [(), ("compose.container.yml",), ("compose.container.yml", "compose.nix.yml")])
def test_the_compose_files_are_valid_for_real(tmp_path: Path, overlays: tuple[str, ...]) -> None:
    """The script's own tests use a fake docker, so only this one proves that Compose can read the files."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    deploy = tmp_path / "deploy"
    (deploy / ".env").write_text("PUBLIC_URL=https://x.test\nSESSION_SECRET=s\nSHELF_RUNNER_TOKEN=t\n")
    files = [arg for name in ("compose.yml", *overlays) for arg in ("-f", name)]
    done = subprocess.run(  # noqa: S603
        ["docker", "compose", "--env-file", ".env", *files, "config", "-q"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=deploy,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr


def test_a_free_port_lets_the_script_go_on_to_build(server: Path) -> None:
    write_env(server)
    assert "Building revision" in run(server).stdout


def test_a_dot_env_at_the_repository_root_is_warned_about(server: Path) -> None:
    write_env(server)
    (server / ".env").write_text("X=1\n")
    assert "only" in run(server).stderr
    assert ".env at the repository root" in run(server).stderr


def test_the_script_says_while_the_bind_address_is_unset_that_loopback_is_an_option(server: Path) -> None:
    write_env(server)
    assert "WEB_BIND=127.0.0.1" in run(server).stdout
    write_env(server, WEB_BIND="127.0.0.1")
    assert "WEB_BIND=127.0.0.1 in" not in run(server).stdout


def test_an_access_file_in_the_old_place_moves_into_the_mounted_folder(server: Path) -> None:
    write_env(server)
    old = server / "deploy" / "shelf.toml"
    old.write_text('[access]\nusers = ["alice"]\n')
    done = run(server)
    assert "Moved" in done.stdout
    assert not old.exists()
    assert "alice" in (server / "deploy" / "config" / "shelf.toml").read_text()


def test_a_first_install_creates_the_access_file_in_the_mounted_folder(server: Path) -> None:
    write_env(server)
    run(server)
    assert (server / "deploy" / "config" / "shelf.toml").exists()


def test_the_catalog_is_created_from_the_example_and_synced_after_the_containers_are_up(server: Path) -> None:
    write_env(server)
    done = run(server)
    assert done.returncode == 0
    assert (server / "deploy" / "config" / "catalog.toml").read_text() == (
        server / "deploy" / "catalog.toml.example"
    ).read_text()
    calls = (server / "docker.log").read_text().splitlines()
    up = next(i for i, line in enumerate(calls) if " up " in f" {line} ")
    sync = next(i for i, line in enumerate(calls) if "run" in line.split() and "catalog" in line.split())
    assert sync > up


def test_the_catalog_image_is_rebuilt_before_it_syncs_so_it_never_runs_an_older_one(server: Path) -> None:
    write_env(server)
    assert run(server).returncode == 0
    calls = (server / "docker.log").read_text().splitlines()
    build = next(i for i, line in enumerate(calls) if "build" in line.split() and "catalog" in line.split())
    sync = next(i for i, line in enumerate(calls) if "run" in line.split() and "catalog" in line.split())
    assert build < sync


def test_a_catalog_the_operator_edited_is_never_overwritten(server: Path) -> None:
    write_env(server)
    config = server / "deploy" / "config"
    config.mkdir(parents=True, exist_ok=True)
    (config / "catalog.toml").write_text("# mine\n")
    run(server)
    assert (config / "catalog.toml").read_text() == "# mine\n"


def test_wardens_operator_policy_is_created_from_the_example_and_never_overwritten(server: Path) -> None:
    write_env(server)
    config = server / "deploy" / "config"
    assert run(server).returncode == 0
    created = config / "warden.toml"
    assert created.read_text() == (server / "deploy" / "warden.toml.example").read_text()
    created.write_text("# mine\n")
    run(server)
    assert created.read_text() == "# mine\n"


def test_the_operator_policy_example_is_valid_toml_with_every_line_commented() -> None:
    text = (DEPLOY / "warden.toml.example").read_text()
    assert tomllib.loads(text) == {}, "the example must change nothing until the operator uncomments a part"


def with_doctor(server: Path, output: str) -> None:
    """Make the fake docker answer ``warden doctor`` with ``output``."""
    fake = server / "bin" / "docker"
    fake.write_text(
        '#!/bin/sh\necho "$@" >> "${DOCKER_LOG:-/dev/null}"\n'
        f'case "$*" in *"warden doctor"*) cat <<\'EOF\'\n{output}\nEOF\n;; esac\nexit 0\n'
    )


def test_a_guard_that_is_wired_is_reported(server: Path) -> None:
    write_env(server)
    with_doctor(server, "ok    warden 0.1.0\nok    Claude Code is wired in the managed settings")
    done = run(server)
    assert "Guard: Warden is wired into the agents" in done.stdout
    assert "not fully in force" not in done.stderr


def test_a_guard_that_is_not_wired_is_a_warning_that_repeats_the_line(server: Path) -> None:
    write_env(server)
    with_doctor(server, "ok    warden 0.1.0\nwarn  Claude Code is not wired in any settings file")
    done = run(server)
    assert done.returncode == 0
    assert "the guard (Warden) is not fully in force" in done.stderr
    assert "Claude Code is not wired in any settings file" in done.stderr


def test_the_guard_is_not_asked_when_it_is_switched_off(server: Path) -> None:
    write_env(server, SHELF_WARDEN="off")
    run(server)
    assert "warden doctor" not in (server / "docker.log").read_text()


def test_a_check_that_cannot_run_does_not_fail_the_script(server: Path) -> None:
    write_env(server)
    done = run(server)
    assert done.returncode == 0
    assert "Guard: Warden is wired" not in done.stdout


def test_the_web_service_reads_the_guards_log_but_cannot_change_it() -> None:
    compose = (Path(__file__).parents[2] / "deploy" / "compose.yml").read_text()
    web = compose.split("\n  web:\n", 1)[1].split("\n  worker:\n", 1)[0]
    assert "WARDEN_STATE_DIR: /var/lib/warden" in web
    assert "- warden-state:/var/lib/warden:ro" in web


def test_the_rules_added_from_the_admin_page_live_in_a_volume_only_the_web_service_writes() -> None:
    compose = (Path(__file__).parents[2] / "deploy" / "compose.yml").read_text()
    web = compose.split("\n  web:\n", 1)[1].split("\n  worker:\n", 1)[0]
    worker = compose.split("\n  worker:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "SHELF_GUARD_RULES_DIR: /var/lib/shelf-guard" in web
    assert "- guard-rules:/var/lib/shelf-guard\n" in web
    assert "WARDEN_OVERLAY_POLICY: /var/lib/shelf-guard/warden.ui.toml" in worker
    assert "- guard-rules:/var/lib/shelf-guard:ro" in worker
    assert "\n  guard-rules:\n" in compose.split("\nvolumes:\n", 1)[1]


def test_the_image_has_the_folder_for_the_rules_owned_by_the_agent_user() -> None:
    dockerfile = (Path(__file__).parents[2] / "Dockerfile").read_text()
    assert "mkdir -p /var/lib/shelf-guard && chown shelf:shelf /var/lib/shelf-guard" in dockerfile


def test_the_script_says_when_the_admin_page_can_add_rules(server: Path) -> None:
    write_env(server)
    done = run(server)
    assert "Guard rules: the admin page can add rules" in done.stdout


def test_the_script_warns_when_the_web_service_cannot_write_the_rules(server: Path) -> None:
    write_env(server)
    fake = server / "bin" / "docker"
    fake.write_text(
        '#!/bin/sh\necho "$@" >> "${DOCKER_LOG:-/dev/null}"\ncase "$*" in *"test -w"*) exit 1;; esac\nexit 0\n'
    )
    done = run(server)
    assert done.returncode == 0
    assert "the admin page cannot write the guard's rules" in done.stderr


def test_the_script_does_not_look_at_the_rules_when_the_guard_is_switched_off(server: Path) -> None:
    write_env(server, SHELF_WARDEN="off")
    assert "Guard rules" not in run(server).stdout


def test_the_nix_overlay_gives_the_daemon_the_store_and_the_worker_only_a_read_only_copy() -> None:
    overlay = (DEPLOY / "compose.nix.yml").read_text()
    daemon = overlay.split("\n  nix:\n", 1)[1].split("\n  worker:\n", 1)[0]
    worker = overlay.split("\n  worker:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "${SHELF_NIX_STORE:-nix-store}:/nix\n" in daemon
    assert "${SHELF_NIX_STORE:-nix-store}:/nix:ro" in worker
    assert "trusted-users = root" in daemon
    assert "min-free" in daemon
    assert "service_healthy" in worker
    assert "  nix-store:" in overlay.split("\nvolumes:\n", 1)[1]
    assert "env_file" not in daemon, "no secret reaches the daemon"


def test_nix_is_not_part_of_a_normal_install(server: Path) -> None:
    write_env(server)
    run(server)
    assert "compose.nix.yml" not in (server / "docker.log").read_text()


def test_asking_for_nix_adds_the_overlay_and_the_script_says_the_worker_reaches_the_daemon(server: Path) -> None:
    write_env(server, SHELF_NIX="on")
    done = run(server)
    assert "compose.nix.yml" in (server / "docker.log").read_text()
    assert "Nix: the worker reaches the Nix daemon" in done.stdout


def test_the_script_warns_when_the_worker_cannot_reach_the_nix_daemon(server: Path) -> None:
    write_env(server, SHELF_NIX="on")
    fake = server / "bin" / "docker"
    fake.write_text(
        '#!/bin/sh\necho "$@" >> "${DOCKER_LOG:-/dev/null}"\ncase "$*" in *"store info"*) exit 1;; esac\nexit 0\n'
    )
    done = run(server)
    assert done.returncode == 0
    assert "the worker cannot reach the Nix daemon" in done.stderr


def test_the_overlay_is_a_file_next_to_the_install_script() -> None:
    assert (DEPLOY / "compose.nix.yml").is_file()


def test_container_mode_is_not_part_of_a_normal_install(server: Path) -> None:
    write_env(server)
    run(server)
    log = (server / "docker.log").read_text()
    assert "compose.container.yml" not in log
    assert "SHELF_RUNNER_TOKEN" not in (server / "deploy" / ".env").read_text()


def test_asking_for_containers_adds_the_overlay_builds_the_step_image_and_writes_a_token(server: Path) -> None:
    write_env(server, SHELF_ISOLATION="container")
    (server / "bin" / "docker").write_text(
        '#!/bin/sh\necho "$@" >> "${DOCKER_LOG:-/dev/null}"\ncase "$*" in *"network inspect"*) exit 1;; esac\nexit 0\n'
    )
    run(server)
    log = (server / "docker.log").read_text()
    assert "compose.container.yml" in log
    assert "--profile tools build step" in log
    assert "network create shelf-sdlc-step" in log
    token = [
        line.split("=", 1)[1]
        for line in (server / "deploy" / ".env").read_text().splitlines()
        if line.startswith("SHELF_RUNNER_TOKEN=")
    ]
    assert len(token) == 1
    assert len(token[0]) >= 32


def test_a_token_that_is_already_there_is_kept(server: Path) -> None:
    write_env(server, SHELF_ISOLATION="container", SHELF_RUNNER_TOKEN="mine")
    run(server)
    assert (server / "deploy" / ".env").read_text().count("SHELF_RUNNER_TOKEN=") == 1
    assert "SHELF_RUNNER_TOKEN=mine" in (server / "deploy" / ".env").read_text()


def test_the_container_overlay_gives_the_runner_the_socket_and_the_worker_only_the_runners_door() -> None:
    overlay = (DEPLOY / "compose.container.yml").read_text()
    runner = overlay.split("\n  runner:\n", 1)[1].split("\n  worker:\n", 1)[0]
    worker = overlay.split("\n  worker:\n", 1)[1].split("\nvolumes:\n", 1)[0]
    assert "/var/run/docker.sock" in runner
    assert "/var/run/docker.sock" not in worker, "only the runner holds the engine's socket"
    assert "read_only: true" in runner
    assert "cap_drop: [ALL]" in runner
    assert "env_file" not in runner, "no secret of the product reaches the runner"
    assert "SHELF_STEP_SET_WARDEN_PROFILE" in runner
    assert "SHELF_ISOLATION: container" in worker


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to resolve the environment")
def test_in_container_mode_only_the_worker_holds_the_runner_key_and_every_service_can_start(tmp_path: Path) -> None:
    """The services share one environment file: web must not need container settings, nor hold the key."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    deploy = tmp_path / "deploy"
    (deploy / ".env").write_text(
        "PUBLIC_URL=https://x.test\nSESSION_SECRET=s\nSHELF_ISOLATION=container\nSHELF_RUNNER_TOKEN=the-key\n"
    )
    done = subprocess.run(
        [  # noqa: S607
            "docker", "compose", "--profile", "tools", "--env-file", ".env", "-f", "compose.yml",
            "-f", "compose.container.yml", "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=deploy,
        timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    services = json.loads(done.stdout)["services"]
    web = from_environ(services["web"]["environment"])
    assert web.container is None
    assert not services["web"]["environment"].get("SHELF_RUNNER_TOKEN")
    assert not services["catalog"]["environment"].get("SHELF_RUNNER_TOKEN")
    assert "the-key" not in json.dumps(services["web"]) + json.dumps(services["runner"].get("volumes", ""))
    worker = from_environ(services["worker"]["environment"])
    assert worker.container is not None
    assert worker.container.token == "the-key"


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to resolve the mounts")
def test_every_volume_the_worker_mounts_in_container_mode_is_a_folder_the_image_gives_to_its_user(
    tmp_path: Path,
) -> None:
    """A new named volume takes the owner of the image's folder: without one the non-root worker cannot write in it."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    deploy = tmp_path / "deploy"
    (deploy / ".env").write_text(
        "PUBLIC_URL=https://x.test\nSESSION_SECRET=s\nSHELF_ISOLATION=container\nSHELF_RUNNER_TOKEN=k\n"
    )
    done = subprocess.run(
        [  # noqa: S607
            "docker", "compose", "--env-file", ".env", "-f", "compose.yml", "-f", "compose.container.yml",
            "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=deploy,
        timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    mounts = json.loads(done.stdout)["services"]["worker"]["volumes"]
    named = [m["target"] for m in mounts if m["type"] == "volume" and not m.get("read_only")]
    assert "/var/lib/shelf/steps" in named
    dockerfile = (DEPLOY.parent / "Dockerfile").read_text()
    # the runner-socket volume is the runner's to create, and the worker only connects to it
    for target in (t for t in named if t != "/run/shelf-runner"):
        assert f"mkdir -p {target}" in dockerfile or f" {target} " in dockerfile, target


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to resolve the services")
def test_with_docker_in_steps_on_every_service_still_starts_and_the_runner_and_the_worker_agree(tmp_path: Path) -> None:
    """The services share one environment file: web and the catalog must not refuse a setting that is the worker's."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    deploy = tmp_path / "deploy"
    (deploy / ".env").write_text(
        "PUBLIC_URL=https://x.test\nSESSION_SECRET=s\nSHELF_ISOLATION=container\nSHELF_RUNNER_TOKEN=k\n"
        "SHELF_STEP_DOCKER=on\nSHELF_STEP_RUNTIME=kata\nSHELF_STEP_DOCKER_PROFILE=unconfined\n"
    )
    done = subprocess.run(
        [  # noqa: S607
            "docker", "compose", "--profile", "tools", "--env-file", ".env", "-f", "compose.yml",
            "-f", "compose.container.yml", "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=deploy,
        timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    services = json.loads(done.stdout)["services"]
    assert from_environ(services["web"]["environment"]).container is None
    worker = from_environ(services["worker"]["environment"])
    assert worker.container is not None
    assert worker.container.docker is True
    runner = read_settings(services["runner"]["environment"])
    assert (runner.rules.docker_runtime, runner.rules.docker_image) == ("kata", "shelf-sdlc-step-docker:local")
    assert runner.rules.docker_profile == "unconfined"
    assert services["step-docker"]["build"]["target"] == "step-docker"
    assert services["step-docker"]["image"] == "shelf-sdlc-step-docker:local"


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose to resolve the services")
def test_with_docker_in_steps_off_the_runner_has_no_runtime_for_it(tmp_path: Path) -> None:
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    deploy = tmp_path / "deploy"
    (deploy / ".env").write_text(
        "PUBLIC_URL=https://x.test\nSESSION_SECRET=s\nSHELF_ISOLATION=container\nSHELF_RUNNER_TOKEN=k\n"
    )
    done = subprocess.run(
        [  # noqa: S607
            "docker", "compose", "--env-file", ".env", "-f", "compose.yml", "-f", "compose.container.yml",
            "config", "--format", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=deploy,
        timeout=60,
    )  # fmt: skip
    assert done.returncode == 0, done.stderr
    runner = read_settings(json.loads(done.stdout)["services"]["runner"]["environment"])
    assert runner.rules.docker_runtime == ""


# --- Docker in steps: install.sh asks the host script whether the host is ready (decision 0020) ---

FAKE_HOST_SCRIPT = """#!/bin/sh
echo "host-runtime $*" >> "$HOST_LOG"
case "$1" in
  --check) [ -f "$HOST_READY" ] && exit 0; exit "${HOST_CHECK_FAILS_WITH:-2}";;
  --yes) touch "$HOST_READY"; exit "${HOST_INSTALL_EXIT:-0}";;
  --probe) [ -z "$HOST_PROBE_FAILS" ] || { echo "no profile works" >&2; exit 1; }; echo "profile=${HOST_PROFILE:-standard}"; exit 0;;
esac
"""


def docker_server(server: Path, **env: str) -> Path:
    """The fake host script and a fake ``sudo`` that only logs and runs its command."""
    (server / "deploy" / "host-runtime.sh").write_text(FAKE_HOST_SCRIPT)
    (server / "bin" / "sudo").write_text('#!/bin/sh\necho "sudo $*" >> "$HOST_LOG"\nexec "$@"\n')
    (server / "bin" / "sudo").chmod(0o755)
    (server / "bin" / "id").write_text("#!/bin/sh\necho 1000\n")
    (server / "bin" / "id").chmod(0o755)
    write_env(server, SHELF_ISOLATION="container", SHELF_RUNNER_TOKEN="k", SHELF_STEP_DOCKER="on", **env)
    return server / "host.log"


def run_docker(
    server: Path, *args: str, ready: bool = False, stdin: int | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    (server / "ss.out").write_text("")
    if ready:
        (server / "host.ready").write_text("")
    return subprocess.run(  # noqa: S603
        ["sh", str(server / "deploy" / "install.sh"), *args],  # noqa: S607
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{server / 'bin'}:{os.environ['PATH']}",
            "SS_OUTPUT": str(server / "ss.out"),
            "DOCKER_LOG": str(server / "docker.log"),
            "HOST_LOG": str(server / "host.log"),
            "HOST_READY": str(server / "host.ready"),
            **env,
        },
        check=False,
        timeout=60,
        stdin=subprocess.DEVNULL if stdin is None else stdin,
    )


def test_docker_in_steps_needs_the_container_mode(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    write_env(server, SHELF_STEP_DOCKER="on", SHELF_STEP_RUNTIME="kata")

    done = run_docker(server)

    assert done.returncode == 1
    assert "SHELF_ISOLATION=container" in done.stderr
    assert not (server / "host.log").exists()


def test_docker_in_steps_needs_a_runtime_to_be_named(server: Path) -> None:
    docker_server(server)

    done = run_docker(server)

    assert done.returncode == 1
    assert "SHELF_STEP_RUNTIME" in done.stderr


def test_a_host_that_is_ready_goes_on_and_the_step_image_with_docker_is_built(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server, ready=True)

    assert done.returncode == 0, done.stderr
    assert "host-runtime --check" in (server / "host.log").read_text()
    assert "sudo" not in (server / "host.log").read_text()
    assert "--profile tools build step-docker" in (server / "docker.log").read_text()


def test_a_host_that_is_not_ready_stops_before_building_and_says_what_to_run(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server)

    assert done.returncode == 1
    assert "sudo sh" in done.stderr
    assert "host-runtime.sh" in done.stderr
    assert "--install-runtime" in done.stderr
    assert "Building revision" not in done.stdout
    assert "sudo" not in (server / "host.log").read_text()


def test_the_flag_runs_the_host_script_through_sudo_and_goes_on(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server, "--install-runtime")

    assert done.returncode == 0, done.stderr
    log = (server / "host.log").read_text()
    assert "sudo env SHELF_STEP_RUNTIME=kata sh" in log
    assert "host-runtime.sh --yes" in log
    lines = log.splitlines()
    assert lines.index("host-runtime --check") < next(i for i, line in enumerate(lines) if "--yes" in line)
    assert any(line == "host-runtime --check" for line in lines[lines.index(next(x for x in lines if "--yes" in x)) :])
    assert "Building revision" in done.stdout


def test_an_install_after_which_the_host_is_still_not_ready_stops(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    (server / "deploy" / "host-runtime.sh").write_text(FAKE_HOST_SCRIPT.replace('touch "$HOST_READY"; ', ""))

    done = run_docker(server, "--install-runtime")

    assert done.returncode == 1
    assert "Building revision" not in done.stdout


def test_a_host_that_cannot_do_it_is_not_offered_an_install(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server, "--install-runtime", HOST_CHECK_FAILS_WITH="1")

    assert done.returncode == 1
    assert "sudo" not in (server / "host.log").read_text()


def test_a_person_at_the_terminal_is_asked_and_yes_runs_the_script(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    master, slave = pty.openpty()
    os.write(master, b"y\n")

    done = run_docker(server, stdin=slave)

    assert done.returncode == 0, done.stderr
    assert "Install it now" in done.stdout
    assert "host-runtime.sh --yes" in (server / "host.log").read_text()


def test_a_person_at_the_terminal_who_says_no_changes_nothing(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    master, slave = pty.openpty()
    os.write(master, b"n\n")

    done = run_docker(server, stdin=slave)

    assert done.returncode == 1
    assert "sudo" not in (server / "host.log").read_text()


def test_the_host_script_is_never_asked_when_docker_in_steps_is_off(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    write_env(server, SHELF_ISOLATION="container", SHELF_RUNNER_TOKEN="k")

    done = run_docker(server)

    assert done.returncode == 0, done.stderr
    assert not (server / "host.log").exists()
    assert "step-docker" not in (server / "docker.log").read_text()


def test_the_flag_does_not_replace_the_address_of_a_first_install(server: Path) -> None:
    (server / "ss.out").write_text("")

    done = run_docker(server, "--install-runtime", "https://shelf.example.org")

    assert done.returncode == 0, done.stderr
    assert "PUBLIC_URL=https://shelf.example.org" in (server / "deploy" / ".env").read_text()


def profile_of(server: Path) -> list[str]:
    env = (server / "deploy" / ".env").read_text().splitlines()
    return [line for line in env if line.startswith("SHELF_STEP_DOCKER_PROFILE=")]


def test_the_profile_the_host_needs_is_found_and_written_into_the_environment_file(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server, ready=True, HOST_PROFILE="unconfined")

    assert done.returncode == 0, done.stderr
    assert profile_of(server) == ["SHELF_STEP_DOCKER_PROFILE=unconfined"]
    assert "--probe" in (server / "host.log").read_text()


def test_a_profile_that_is_already_set_is_never_probed_again(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata", SHELF_STEP_DOCKER_PROFILE="full")

    done = run_docker(server, ready=True, HOST_PROFILE="unconfined")

    assert done.returncode == 0, done.stderr
    assert profile_of(server) == ["SHELF_STEP_DOCKER_PROFILE=full"]
    assert "--probe" not in (server / "host.log").read_text()


def test_the_second_run_does_not_probe_again(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    run_docker(server, ready=True, HOST_PROFILE="unconfined")
    (server / "host.log").unlink()

    done = run_docker(server, ready=True, HOST_PROFILE="full")

    assert done.returncode == 0, done.stderr
    assert profile_of(server) == ["SHELF_STEP_DOCKER_PROFILE=unconfined"]
    assert "--probe" not in (server / "host.log").read_text()


def test_a_host_where_no_profile_works_stops_before_building(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")

    done = run_docker(server, ready=True, HOST_PROBE_FAILS="1")

    assert done.returncode == 1
    assert "Docker in steps" in done.stderr
    assert profile_of(server) == []
    assert "Building revision" not in done.stdout


def test_the_probe_is_not_asked_when_docker_in_steps_is_off(server: Path) -> None:
    docker_server(server, SHELF_STEP_RUNTIME="kata")
    write_env(server, SHELF_ISOLATION="container", SHELF_RUNNER_TOKEN="k")

    run_docker(server)

    assert not (server / "host.log").exists()
