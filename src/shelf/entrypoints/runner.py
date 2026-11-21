"""``shelf-runner``: the service that holds the container engine's socket and starts each step in a container.

It reads its own settings (it never reads the worker's), refuses to start without a caller token or an engine it can
read, removes what expired while it was away, and serves on a unix socket in a volume it shares with the worker only.
"""

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from shelf.adapters.container_runner.app import create_app
from shelf.adapters.container_runner.engine import DockerEngine
from shelf.adapters.container_runner.service import StepService
from shelf.domain.stepspec import CONFIG_TARGETS, VARIABLE, Limits, RunnerRules
from shelf.ports.container_engine import EngineError

log = logging.getLogger("shelf.runner")
REAP_EVERY = 60.0


class RunnerSettingsError(ValueError):
    """A setting of the runner is missing or wrong. The message names the variable, never its value."""


@dataclass(frozen=True, slots=True)
class RunnerSettings:
    """What the operator set for the runner."""

    socket: str
    engine_socket: str
    token: str | None
    """``None`` only when the operator set ``SHELF_RUNNER_INSECURE=1``, which the tests use."""
    rules: RunnerRules


def _number(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        message = f"{name} must be a number"
        raise RunnerSettingsError(message) from None
    if value <= 0:
        message = f"{name} must be above zero"
        raise RunnerSettingsError(message)
    return value


SET_PREFIX = "SHELF_STEP_SET_"


def _config(environ: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """``SHELF_STEP_CONFIG``: ``volume:target`` pairs, each mounted read-only, each at a place the product reads."""
    mounts: list[tuple[str, str]] = []
    for item in (part.strip() for part in environ.get("SHELF_STEP_CONFIG", "").split(",")):
        if not item:
            continue
        volume, _, target = item.partition(":")
        if not volume or target not in CONFIG_TARGETS:
            message = f"SHELF_STEP_CONFIG takes volume:target, and a target is one of {', '.join(CONFIG_TARGETS)}"
            raise RunnerSettingsError(message)
        mounts.append((volume, target))
    return tuple(mounts)


def _fixed_env(environ: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
    """Every ``SHELF_STEP_SET_<NAME>`` is ``<NAME>`` in each step: how the operator sets the guard's variables."""
    names = sorted(key.removeprefix(SET_PREFIX) for key in environ if key.startswith(SET_PREFIX))
    if bad := [name for name in names if VARIABLE.fullmatch(name) is None]:
        message = f"{SET_PREFIX}{bad[0][:40]} is not a variable name"
        raise RunnerSettingsError(message)
    return tuple((name, environ[f"{SET_PREFIX}{name}"]) for name in names)


def read_settings(environ: Mapping[str, str]) -> RunnerSettings:
    """The runner's settings from the environment, or ``RunnerSettingsError``."""
    image = environ.get("SHELF_STEP_IMAGE", "").strip()
    if not image:
        message = "SHELF_STEP_IMAGE must name the image a step runs in"
        raise RunnerSettingsError(message)
    token = environ.get("SHELF_RUNNER_TOKEN", "").strip()
    if not token and environ.get("SHELF_RUNNER_INSECURE") != "1":
        message = "SHELF_RUNNER_TOKEN is needed: the runner holds the engine socket and answers only to its caller"
        raise RunnerSettingsError(message)
    ceiling = Limits(
        cpus=_number(environ, "SHELF_STEP_CPUS", Limits().cpus),
        memory_mb=int(_number(environ, "SHELF_STEP_MEMORY_MB", Limits().memory_mb)),
        pids=int(_number(environ, "SHELF_STEP_PIDS", Limits().pids)),
        tmp_mb=int(_number(environ, "SHELF_STEP_TMP_MB", Limits().tmp_mb)),
        seconds=int(_number(environ, "SHELF_STEP_SECONDS", Limits().seconds)),
    )
    defaults = RunnerRules(image=image)
    rules = RunnerRules(
        image=image,
        network=environ.get("SHELF_STEP_NETWORK", defaults.network),
        steps_volume=environ.get("SHELF_STEPS_VOLUME", defaults.steps_volume),
        tools_volume=environ.get("SHELF_TOOLS_VOLUME", defaults.tools_volume),
        sessions_volume=environ.get("SHELF_SESSIONS_VOLUME", defaults.sessions_volume),
        limits=ceiling,
        config=_config(environ),
        fixed_env=_fixed_env(environ),
    )
    return RunnerSettings(
        socket=environ.get("SHELF_RUNNER_SOCKET", "/run/shelf-runner/runner.sock"),
        engine_socket=environ.get("SHELF_ENGINE_SOCKET", "/var/run/docker.sock"),
        token=token or None,
        rules=rules,
    )


async def _reap_forever(service: StepService) -> None:
    while True:
        await asyncio.sleep(REAP_EVERY)
        try:
            await service.reap()
        except EngineError as error:
            log.warning("could not look for expired steps: %s", error)


async def serve(settings: RunnerSettings) -> None:
    """Check the engine, remove what expired, and serve until stopped."""
    service = StepService(DockerEngine(settings.engine_socket), settings.rules)
    removed = await service.reap()
    log.info("the engine is readable; removed %d expired steps", removed)
    app = create_app(service, settings.rules, settings.token)
    Path(settings.socket).parent.mkdir(parents=True, exist_ok=True)
    reaper = asyncio.create_task(_reap_forever(service))
    try:
        await uvicorn.Server(uvicorn.Config(app, uds=settings.socket, log_level="info")).serve()
    finally:
        reaper.cancel()


def main() -> int:
    """Start the runner. Exits with a message, never a traceback, for a setting or the engine."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        settings = read_settings(os.environ)
        asyncio.run(serve(settings))
    except (RunnerSettingsError, EngineError) as error:
        log.error("%s", error)  # noqa: TRY400
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
