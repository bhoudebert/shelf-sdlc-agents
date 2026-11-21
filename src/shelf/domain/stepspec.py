"""What the runner accepts for a step and the container it builds from it (decision 0019). Pure: no I/O, no clock.

A request has a fixed shape. It has no field for mounts, capabilities, devices, ports, user, network, privileged mode or
any engine option: the container is built here, from the request's few names and the operator's rules, so what a
step can do is decided in one place that a test can read.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import Any, Final, cast

from shelf.domain.mise_config import NO_CODE_AT_INSTALL
from shelf.domain.result import Err, Ok, Result
from shelf.domain.toolchain import repository_folder

KEY: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}")
REPO: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}")
"""GitHub owners have no underscore, so ``tools_path`` cannot give two repositories the same folder."""
CLONE: Final = re.compile(r"steps/[a-z0-9][a-z0-9_-]{0,63}/repo")
"""A folder of the clones volume that holds one clone, as the worker makes it: ``steps/<name>/repo``."""
SESSION: Final = re.compile(r"work/[a-z0-9][a-z0-9-]{0,63}")
VARIABLE: Final = re.compile(r"[A-Z][A-Z0-9_]{0,63}")

FIELDS: Final = frozenset({"key", "kind", "repo", "clone", "session", "mode", "limits", "env", "input", "docker"})
KINDS: Final = ("agent",)
"""The kinds the runner can run. ``check`` and ``setup`` come with the volumes of stage 3."""
LIMITS: Final = ("cpus", "memory_mb", "pids", "tmp_mb", "seconds")

WORKDIR: Final = "/work"
HOME: Final = "/home/step"
TASK_DIR: Final = "/run/shelf"
TASK_FILE: Final = "task.json"
USER: Final = "1000:1000"
DOCKER_STORAGE: Final = "/var/lib/docker"
"""Where the step's own Docker daemon keeps its images and containers: a volume of the step that goes with it."""
DOCKER_CAPS: Final = ("SYS_ADMIN", "NET_ADMIN", "SYS_RESOURCE", "MKNOD")
"""What a daemon needs in the step's own kernel, added to Docker's default set. The runtime keeps them off the host."""
DOCKER_COMMAND: Final = "shelf-step-docker"
"""The wrapper that starts the step's daemon as root and then runs the step as its own user."""
TOOLS: Final = (".local/share/mise", ".m2", ".npm", ".cache")
"""Where a repository's tools and caches live in a step, and in the repository's home in the tools volume."""
CONFIG_TARGETS: Final = ("/etc/claude-code", "/opt/shelf/catalog", "/var/lib/shelf-guard", "/etc/shelf")
"""The only places a config volume may be mounted: where the product reads its policy, catalog and guard rules."""


ENV_ALLOWED: Final = ("ANTHROPIC_*", "CLAUDE_CODE_*", "GH_TOKEN", "GITHUB_TOKEN", "SHELF_STEP_*")
"""The patterns of the variables a request may give a step: the worker sends only these, the runner refuses the rest."""


@dataclass(frozen=True, slots=True)
class Limits:
    """What one step may use. The operator's value is the ceiling; a request may ask for less."""

    cpus: float = 4.0
    memory_mb: int = 6144
    pids: int = 2048
    tmp_mb: int = 2048
    seconds: int = 2700

    def clamped(self, asked: Mapping[str, float | int]) -> "Limits":
        """These limits lowered to what ``asked`` names, never raised."""
        return Limits(
            cpus=min(self.cpus, float(asked.get("cpus", self.cpus))),
            memory_mb=min(self.memory_mb, int(asked.get("memory_mb", self.memory_mb))),
            pids=min(self.pids, int(asked.get("pids", self.pids))),
            tmp_mb=min(self.tmp_mb, int(asked.get("tmp_mb", self.tmp_mb))),
            seconds=min(self.seconds, int(asked.get("seconds", self.seconds))),
        )


@dataclass(frozen=True, slots=True)
class RunnerRules:
    """What the operator decided: the image, the network, the volumes and the ceilings. Never from a request."""

    image: str
    network: str = "shelf-step"
    steps_volume: str = "shelf-steps"
    tools_volume: str = "shelf-tools"
    sessions_volume: str = "shelf-sessions"
    limits: Limits = field(default_factory=Limits)
    env_allowed: tuple[str, ...] = ENV_ALLOWED
    """Patterns an ``env`` name must match. Anything else is refused."""
    config: tuple[tuple[str, str], ...] = ()
    """``(volume, target)`` of each read-only config volume: the managed policy, the catalog, the guard's rules."""
    fixed_env: tuple[tuple[str, str], ...] = ()
    """Variables set in every step from the operator's rules, never from a request: the guard's profile and paths."""
    docker_runtime: str = ""
    """The runtime that makes a Docker daemon inside a step safe (decision 0020). Empty: no step has Docker."""
    docker_image: str = ""
    """The image of a step with a Docker daemon; the plain step image when empty."""


@dataclass(frozen=True, slots=True)
class StepAsk:
    """A request that passed the rules."""

    key: str
    kind: str
    repo: str
    clone: str
    session: str
    tools_readonly: bool
    clone_readonly: bool
    limits: Limits
    env: Mapping[str, str]
    input: Mapping[str, Any]
    docker: bool = False
    """The step has a Docker daemon of its own. Only a runner with a runtime for it accepts it."""


def _object(value: object) -> dict[str, Any] | None:
    """``value`` as an object with text keys, or ``None`` when it is not an object."""
    if not isinstance(value, dict):
        return None
    return {str(k): v for k, v in cast("dict[object, Any]", value).items()}


def _name(data: Mapping[str, Any], key: str, pattern: re.Pattern[str], *, required: bool) -> Result[str, str]:
    value = data.get(key, "")
    if value == "" and not required:
        return Ok("")
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        return Err(f"the field {key} is missing or does not match its rules")
    if ".." in value.split("/"):
        return Err(f"the field {key} may not go up a folder")
    return Ok(value)


def _mode(data: Mapping[str, Any]) -> Result[tuple[bool, bool], str]:
    modes = _object(data.get("mode", {}))
    if modes is None:
        return Err("the field mode is not an object")
    if set(modes) - {"tools", "clone"}:
        return Err("the field mode may only name tools and clone")
    if any(value not in ("ro", "rw") for value in modes.values()):
        return Err("the field mode takes ro or rw")
    return Ok((modes.get("tools") == "ro", modes.get("clone") == "ro"))


def _limits(data: Mapping[str, Any], ceiling: Limits) -> Result[Limits, str]:
    given = _object(data.get("limits", {}))
    if given is None:
        return Err("the field limits is not an object")
    asked: dict[str, float | int] = {}
    for name, value in given.items():
        if name not in LIMITS:
            return Err("the field limits names something the runner does not limit")
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            return Err(f"the limit {name} is not a positive number")
        asked[str(name)] = value
    return Ok(ceiling.clamped(asked))


def _env(data: Mapping[str, Any], allowed: tuple[str, ...]) -> Result[dict[str, str], str]:
    given = _object(data.get("env", {}))
    if given is None:
        return Err("the field env is not an object")
    env: dict[str, str] = {}
    for name, value in given.items():
        if VARIABLE.fullmatch(name) is None:
            return Err("the field env holds a name that is not a variable name")
        if not any(fnmatchcase(name, pattern) for pattern in allowed):
            return Err(f"the environment variable {name} is not one a step may be given")
        if not isinstance(value, str):
            return Err(f"the environment variable {name} is not text")
        env[name] = value
    return Ok(env)


def _docker(data: Mapping[str, Any], rules: RunnerRules) -> Result[bool, str]:
    wanted = data.get("docker", False)
    if not isinstance(wanted, bool):
        return Err("the field docker is not true or false")
    if wanted and not rules.docker_runtime:
        return Err("the field docker is refused: this runner has no runtime for a Docker daemon in a step")
    return Ok(wanted)


def _shape(data: object) -> Result[dict[str, Any], str]:
    body = _object(data)
    if body is None:
        return Err("the request is not an object")
    if unknown := sorted(set(body) - FIELDS):
        return Err(f"the request has a field the runner does not accept: {unknown[0][:40]}")
    if body.get("kind", "agent") not in KINDS:
        return Err(f"the kind must be one of {', '.join(KINDS)}")
    if _object(body.get("input", {})) is None:
        return Err("the field input is not an object")
    return Ok(body)


def _first_error(*results: Result[Any, str]) -> str | None:
    return next((result.error for result in results if isinstance(result, Err)), None)


def parse_request(data: object, rules: RunnerRules) -> Result[StepAsk, str]:
    """The request as a ``StepAsk``, or the first rule it breaks. The message names a field, never a value."""
    shape = _shape(data)
    if isinstance(shape, Err):
        return shape
    body = shape.value
    key = _name(body, "key", KEY, required=True)
    repo = _name(body, "repo", REPO, required=True)
    clone = _name(body, "clone", CLONE, required=True)
    session = _name(body, "session", SESSION, required=False)
    mode, limits, env = _mode(body), _limits(body, rules.limits), _env(body, rules.env_allowed)
    docker = _docker(body, rules)
    if broken := _first_error(key, repo, clone, session, mode, limits, env, docker):
        return Err(broken)
    # every result above is Ok here; the isinstance checks narrow the types for the reader and the checker
    if not (
        isinstance(key, Ok)
        and isinstance(repo, Ok)
        and isinstance(clone, Ok)
        and isinstance(session, Ok)
        and isinstance(mode, Ok)
        and isinstance(limits, Ok)
        and isinstance(env, Ok)
        and isinstance(docker, Ok)
    ):
        return Err("the request is not valid")
    return Ok(
        StepAsk(
            key=key.value,
            kind=str(body.get("kind", "agent")),
            repo=repo.value,
            clone=clone.value,
            session=session.value,
            tools_readonly=mode.value[0],
            clone_readonly=mode.value[1],
            limits=limits.value,
            env=env.value,
            input=_object(body.get("input", {})) or {},
            docker=docker.value,
        )
    )


def tools_path(repo: str) -> str:
    """The repository's home in the tools volume: where the worker's own set-up installs the tools."""
    return repository_folder(repo)


def _mount(source: str, target: str, subpath: str, *, readonly: bool) -> dict[str, Any]:
    mount: dict[str, Any] = {"Type": "volume", "Source": source, "Target": target, "ReadOnly": readonly}
    if subpath:
        mount["VolumeOptions"] = {"Subpath": subpath}
    return mount


def labels_of(ask: StepAsk, *, expires: int) -> dict[str, str]:
    """The labels every container of the runner carries, so a restart can find what it owns and what expired."""
    return {"shelf.managed": "true", "shelf.step": ask.key, "shelf.expires": str(expires)}


def _fixed_env(rules: RunnerRules) -> list[str]:
    """What every step gets whatever it asked: its home, the tool installer's settings and the operator's own."""
    fixed = {
        "HOME": HOME,
        "MISE_YES": "1",
        "MISE_LOCKFILE": "false",
        "MISE_DISABLE_BACKENDS": NO_CODE_AT_INSTALL,
        "MISE_TRUSTED_CONFIG_PATHS": WORKDIR,
        **dict(rules.fixed_env),
    }
    return [f"{name}={value}" for name, value in fixed.items()]


def container_spec(ask: StepAsk, rules: RunnerRules, *, expires: int) -> dict[str, Any]:
    """The engine's request to create the container: fixed by this function, never by the request.

    ``expires`` is when the container is due to be gone, in seconds since the epoch; the caller owns the clock.
    """
    mounts = [
        _mount(rules.steps_volume, WORKDIR, ask.clone, readonly=ask.clone_readonly),
        *(
            _mount(
                rules.tools_volume, f"{HOME}/{folder}", f"{tools_path(ask.repo)}/{folder}", readonly=ask.tools_readonly
            )
            for folder in TOOLS
        ),
        {"Type": "volume", "Target": TASK_DIR},
        *(_mount(volume, target, "", readonly=True) for volume, target in rules.config),
    ]
    if ask.session:
        mounts.append(_mount(rules.sessions_volume, f"{HOME}/.claude/projects", ask.session, readonly=False))
    limits = ask.limits
    host: dict[str, Any] = {
        "ReadonlyRootfs": True,
        "CapDrop": ["ALL"],
        "SecurityOpt": ["no-new-privileges"],
        "Init": True,
        "Privileged": False,
        "PidsLimit": limits.pids,
        "Memory": limits.memory_mb * 1024 * 1024,
        "MemorySwap": limits.memory_mb * 1024 * 1024,
        "NanoCpus": int(limits.cpus * 1_000_000_000),
        "Tmpfs": {"/tmp": f"rw,nosuid,size={limits.tmp_mb}m"},  # noqa: S108
        "Mounts": mounts,
        "NetworkMode": rules.network,
        "PublishAllPorts": False,
        "AutoRemove": False,
    }
    body: dict[str, Any] = {
        "Image": rules.image,
        "Cmd": ["shelf-step", f"{TASK_DIR}/{TASK_FILE}"],
        "User": USER,
        "WorkingDir": WORKDIR,
        "Env": [f"{name}={value}" for name, value in ask.env.items()] + _fixed_env(rules),
        "Labels": labels_of(ask, expires=expires),
        "AttachStdout": True,
        "AttachStderr": True,
        "Tty": False,
        "NetworkDisabled": False,
        "HostConfig": host,
    }
    return _with_docker(body, rules) if ask.docker else body


def _with_docker(body: dict[str, Any], rules: RunnerRules) -> dict[str, Any]:
    """The same container with a Docker daemon of its own, under the operator's runtime (decision 0020).

    The daemon runs as root inside the step's own kernel, so the runtime is what keeps it from the host: the container
    is still not privileged against the host, has no device, no host path and no engine socket, and its storage is a
    volume that goes with it. The wrapper starts the daemon and runs the step as the step's user.
    """
    host = dict(body["HostConfig"])
    host["Runtime"] = rules.docker_runtime
    host["CapDrop"] = []
    host["CapAdd"] = list(DOCKER_CAPS)
    host["Tmpfs"] = {**host["Tmpfs"], "/run": "rw,nosuid,size=64m"}
    host["Mounts"] = [*host["Mounts"], {"Type": "volume", "Target": DOCKER_STORAGE}]
    command = [DOCKER_COMMAND, *body["Cmd"][1:]]
    return {**body, "Image": rules.docker_image or rules.image, "User": "0:0", "Cmd": command, "HostConfig": host}
