import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

DEPLOY = Path(__file__).parents[2] / "deploy"


@pytest.fixture
def server(tmp_path: Path) -> Path:
    """A copy of deploy/ next to fake ``docker`` and ``ss`` programs, so the script runs without building anything."""
    shutil.copytree(DEPLOY, tmp_path / "deploy")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in {
        "docker": 'echo "$@" >> "${DOCKER_LOG:-/dev/null}"; exit 0',
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


def run(server: Path, busy: str = "") -> subprocess.CompletedProcess[str]:
    (server / "ss.out").write_text(busy)
    env = {
        **os.environ,
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
