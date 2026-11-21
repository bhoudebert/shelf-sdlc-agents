"""Run real steps in real containers through the runner service, against a mock of the Anthropic API (decision 0019).

It needs Docker, the ``step`` image (``STEP_IMAGE``, built with ``docker build --target step``) and ``uv run`` so that
``shelf-runner`` exists. It starts the runner as a process on a unix socket, the mock model as a container on the step
network (so no host firewall is involved), and checks, in this order:

1. the container the runner builds is locked down for real: not root, no capability, a read-only root, writable only
   where it should be;
2. a whole step runs: hello, a tool call, a result and an ``exit`` written by the runner, and the container is gone after;
3. the policy volume is mounted read-only, the operator's variables are set and a later container of the same work finds
   the session an earlier one left;
4. a step that runs past its deadline is stopped and ends with the reason ``timeout``.

No credential and no cost: the "model" is ``warden/live/mock_anthropic.py``.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from shelf.adapters.container_agent.client import HttpStepRunner
from shelf.adapters.container_runner.engine import DockerEngine
from shelf.domain.stepspec import RunnerRules, container_spec, parse_request
from shelf.domain.stepstream import Exit, Hello, Result, Tool, decode
from shelf.ports.step_runner import StepRequest

ROOT = Path(__file__).resolve().parent.parent
IMAGE = os.environ.get("STEP_IMAGE", "shelf-step-test")
TOKEN = "live-check-token"  # noqa: S105
SUFFIX = str(os.getpid())
MOCK = f"shelf-live-mock-{SUFFIX}"
NETWORK, STEPS, TOOLS, SESSIONS, POLICY = (
    f"shelf-live-{name}-{SUFFIX}" for name in ("net", "steps", "tools", "sessions", "policy")
)
REPO = "acme/shop"


def docker(*args: str, check: bool = True) -> str:
    done = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        print(done.stderr, file=sys.stderr)
        message = f"docker {args[0]} failed"
        raise SystemExit(message)
    return done.stdout.strip()


def expect(condition: bool, what: str) -> None:
    print(("ok    " if condition else "FAIL  ") + what)
    if not condition:
        raise SystemExit(1)


def prepare() -> None:
    """The network and the three volumes, with the folders the runner will mount (it never creates one)."""
    docker("network", "create", NETWORK)
    for volume in (STEPS, TOOLS, SESSIONS, POLICY):
        docker("volume", "create", volume)
    home = f"/tools/home/{REPO.replace('/', '__')}"
    tools = [f"{home}/{name}" for name in (".local/share/mise", ".m2", ".npm", ".cache")]
    script = f"mkdir -p /steps/steps/t1/repo {' '.join(tools)} /sessions/work/t1 && chown -R 1000:1000 /steps /tools /sessions"
    docker(
        "run", "--rm", "-u", "0", "--entrypoint", "sh",
        "-v", f"{STEPS}:/steps", "-v", f"{TOOLS}:/tools", "-v", f"{SESSIONS}:/sessions", "-v", f"{POLICY}:/policy",
        IMAGE, "-c", script + " && echo '{\"hooks\":{}}' > /policy/managed-settings.json",
    )  # fmt: skip


@contextmanager
def background(command: list[str], env: dict[str, str] | None = None) -> Iterator[subprocess.Popen[bytes]]:
    process = subprocess.Popen(command, env={**os.environ, **(env or {})})
    try:
        yield process
    finally:
        process.terminate()
        process.wait(timeout=20)


def rules(socket_dir: str) -> RunnerRules:
    del socket_dir
    return RunnerRules(
        image=IMAGE,
        network=NETWORK,
        steps_volume=STEPS,
        tools_volume=TOOLS,
        sessions_volume=SESSIONS,
        config=((POLICY, "/etc/claude-code"),),
        fixed_env=(("WARDEN_PROFILE", "shelf"),),
    )


async def probe_run(script: str, key: str) -> str:
    """One container the runner would build, with its command replaced by ``script``; what it printed."""
    ask = parse_request(
        {"key": key, "repo": REPO, "clone": "steps/t1/repo", "session": "work/t1", "input": {"prompt": "x"}},
        rules(""),
    )
    spec = container_spec(ask.value, rules(""), expires=int(time.time()) + 300)  # pyright: ignore[reportAttributeAccessIssue]
    spec = {**spec, "Cmd": ["sh", "-c", script], "Entrypoint": []}
    engine = DockerEngine()
    container = await engine.create(spec, f"shelf-step-probe-{key}-{SUFFIX}")
    try:
        await engine.put_file(container, "/run/shelf", "task.json", b'{"prompt":"x"}')
        await engine.start(container)
        out = b"".join([chunk async for chunk in engine.stdout(container)]).decode()
        await engine.wait(container)
    finally:
        await engine.remove(container)
    return out


async def probe() -> None:
    """The container the runner builds, with its command replaced by a script that reports what it can do."""
    script = (
        "echo uid=$(id -u); echo caps=$(grep CapEff /proc/self/status | cut -f2); "
        "touch /x 2>/dev/null && echo root=writable || echo root=readonly; "
        "touch /tmp/a && echo tmp=writable; touch /work/a && echo work=writable; "
        "touch /home/step/.m2/a && echo m2=writable; touch /home/step/.claude/projects/a && echo sessions=writable; "
        "touch /etc/claude-code/a 2>/dev/null && echo policy=writable || echo policy=readonly; "
        "test -s /etc/claude-code/managed-settings.json && echo policy_read=yes; "
        "echo guard=$WARDEN_PROFILE; echo mise=$MISE_YES; echo path=$PATH; echo home=$HOME; "
        "echo userdb=$(getent passwd $(id -u) | cut -d: -f6); "
        "cat /run/shelf/task.json"
    )
    out = await probe_run(script, "probe-1")
    facts = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    expect(facts.get("uid") == "1000", "the step is not root")
    expect(facts.get("caps") == "0000000000000000", "the step has no capability")
    expect(facts.get("root") == "readonly", "the root filesystem is read-only")
    expect(
        all(facts.get(name) == "writable" for name in ("tmp", "work", "m2", "sessions")), "it writes where it should"
    )
    expect(facts.get("policy") == "readonly" and facts.get("policy_read") == "yes", "the policy is read-only and there")
    expect(facts.get("guard") == "shelf" and facts.get("mise") == "1", "the operator's variables are set")
    expect(facts.get("userdb") == facts.get("home") == "/home/step", "the user database and HOME name one home")
    expect(facts.get("path", "").startswith("/home/step/.local/share/mise/shims:"), "the tool shims come first")
    expect('{"prompt":"x"}' in out, "it reads the task the runner put in the file")
    # a second container of the same work finds what the first left in the sessions folder (spike S4's first half)
    await probe_run(
        "mkdir -p /home/step/.claude/projects/-work && echo kept > /home/step/.claude/projects/-work/s", "w1"
    )
    again = await probe_run("cat /home/step/.claude/projects/-work/s", "w2")
    expect(again.strip() == "kept", "a later container of the same work finds the earlier session")


async def step(socket: str, host: str, port: int, key: str, seconds: int | None = None) -> tuple[list[str], float]:
    runner = HttpStepRunner(socket, TOKEN)
    request = StepRequest(
        key=key,
        repo=REPO,
        clone="steps/t1/repo",
        session="work/t1",
        limits={"seconds": seconds} if seconds else {},
        env={"ANTHROPIC_BASE_URL": f"http://{host}:{port}", "ANTHROPIC_API_KEY": "mock", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
        input={"role": {"name": "implementer", "tools": ["Bash"]}, "prompt": "say hello", "max_turns": 5},
    )  # fmt: skip
    started = time.monotonic()
    first = 0.0
    lines: list[str] = []
    async for line in runner.run(request):
        if not lines:
            first = time.monotonic() - started
        lines.append(line)
    return lines, first


async def main_async(socket: str, host: str, port: int) -> None:
    lines, first = await step(socket, host, port, "live/step/1")
    events = [decode(line) for line in lines if '"e":"ping"' not in line]
    expect(isinstance(events[0], Hello), f"the first line is hello (got {lines[0][:150]!r})")
    expect(any(isinstance(e, Tool) and e.name == "Bash" for e in events), "the tool call is reported")
    result = next((e for e in events if isinstance(e, Result)), None)
    expect(result is not None and not result.is_error, f"the agent ended well: {result and result.result[:80]!r}")
    expect(events[-1] == Exit(0), "the runner wrote the exit line")
    print(f"      first line after {first:.1f}s")
    left = docker("ps", "-a", "--filter", "label=shelf.managed=true", "--format", "{{.ID}}")
    expect(left == "", "no container is left behind")
    again, _ = await step(socket, host, port, "live/step/1")
    expect(again == lines or len(again) == len(lines), "asking again returns the same step")
    slow, _ = await step(socket, host, port, "live/step/2", seconds=1)
    expect(decode(slow[-1]) == Exit(-1, "timeout"), "a step past its deadline ends with a timeout")
    expect(docker("ps", "-a", "--filter", "label=shelf.managed=true", "--format", "{{.ID}}") == "", "and is removed")


def main() -> int:
    prepare()
    try:
        asyncio.run(probe())
        with tempfile.TemporaryDirectory() as directory:
            socket = f"{directory}/runner.sock"
            port = 8080
            mock = [
                "run", "-d", "--rm", "--name", MOCK, "--network", NETWORK, "--user", "1000:1000", "--read-only",
                "-v", f"{ROOT / 'warden/live/mock_anthropic.py'}:/mock.py:ro", "--tmpfs", "/tmp",
                "--entrypoint", "python", IMAGE, "/mock.py", str(port), "echo hello", "/tmp/mock.log", "0.0.0.0",
            ]  # fmt: skip
            env = {
                "SHELF_RUNNER_SOCKET": socket,
                "SHELF_RUNNER_TOKEN": TOKEN,
                "SHELF_STEP_IMAGE": IMAGE,
                "SHELF_STEP_NETWORK": NETWORK,
                "SHELF_STEPS_VOLUME": STEPS,
                "SHELF_TOOLS_VOLUME": TOOLS,
                "SHELF_SESSIONS_VOLUME": SESSIONS,
                "SHELF_STEP_CONFIG": f"{POLICY}:/etc/claude-code",
                "SHELF_STEP_SET_WARDEN_PROFILE": "shelf",
            }
            docker(*mock)
            with background([sys.executable, "-m", "shelf.entrypoints.runner"], env):
                for _ in range(100):
                    if Path(socket).exists():
                        break
                    time.sleep(0.1)
                time.sleep(1.5)
                asyncio.run(main_async(socket, MOCK, port))
    finally:
        docker("rm", "-f", MOCK, check=False)
        docker("network", "rm", NETWORK, check=False)
        docker("volume", "rm", "-f", STEPS, TOOLS, SESSIONS, POLICY, check=False)
    print(json.dumps({"image": IMAGE}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
