"""``shelf-doctor``: runs a few tiny real agent checks against this instance's configuration and says what works.

Run it where the worker runs (``docker compose exec worker shelf-doctor``). Every check asks an agent to do one small
thing in a throwaway repository, so a missing credential, a sandbox that cannot start, a refused tool or an ignored
repository file shows up here, in one place, instead of as a confusing sentence inside a pull request.
"""

import asyncio
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from shelf.adapters.claude_agent.backend import ClaudeBackend
from shelf.adapters.claude_agent.prompts import load_prompt
from shelf.domain.pipeline import Phase
from shelf.domain.roles import ROLES, TITLER, AgentRole
from shelf.entrypoints import settings as settings_module
from shelf.ports.agents import AgentBackend, AgentTask

CONVENTIONAL = re.compile(r"^(feat|fix|docs|chore|refactor|test|build|ci|perf|style|revert)(\([^)]+\))?!?: \S")
TURNS = 8
BUDGET = 0.5


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one check found."""

    name: str
    passed: bool
    detail: str
    hint: str = ""


@dataclass(frozen=True, slots=True)
class Check:
    """One thing to ask an agent, and how to tell whether it did it."""

    name: str
    role: AgentRole
    prompt: str
    passes: Callable[[str, Path], bool]
    hint: str
    system: str = "You are a careful assistant. Be brief."


def make_repository(root: Path) -> None:
    """A throwaway repository: two commits in Conventional Commits style and a CLAUDE.md with a rule to follow."""
    run = ["git", "-c", "user.email=doctor@shelf", "-c", "user.name=doctor"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)  # noqa: S603, S607
    (root / "README.md").write_text("# Demo\n")
    subprocess.run([*run, "-C", str(root), "add", "-A"], check=True)  # noqa: S603
    subprocess.run([*run, "-C", str(root), "commit", "-q", "-m", "feat(core): first commit"], check=True)  # noqa: S603
    (root / "README.md").write_text("# Demo\n\nsecond\n")
    subprocess.run([*run, "-C", str(root), "commit", "-qam", "fix(core): second commit"], check=True)  # noqa: S603
    (root / "CLAUDE.md").write_text("CLAUDE-MD-RULE: end every answer with the word PINEAPPLE.\n")


def checks() -> list[Check]:
    """The checks, in the order a problem is most likely to show."""
    return [
        Check(
            "A reviewer can run git",
            ROLES[Phase.CODE_REVIEW],
            "Run `git log --oneline` and quote the subject of the newest commit. If a command is refused, say so.",
            lambda answer, _root: "second commit" in answer,
            "The agents have no shell. Update to the latest release with `sh deploy/install.sh`, then run this again.",
        ),
        Check(
            "The repository's own CLAUDE.md is loaded",
            ROLES[Phase.INTAKE],
            "Say hello in one short sentence.",
            lambda answer, _root: "PINEAPPLE" in answer.upper(),
            "The agents are not reading the repository's CLAUDE.md. Is the worker on the latest release?",
        ),
        Check(
            "The agent that names pull requests follows the repository's convention",
            TITLER,
            "Write the pull request title for a change that fixes a typo in README.md. Answer with the title only.",
            lambda answer, _root: bool(CONVENTIONAL.match(answer.strip().splitlines()[-1].strip("`\"' "))),
            "The title did not follow the Conventional Commits style found in `git log`.",
            system=load_prompt("titler"),
        ),
        Check(
            "The developer can run commands",
            ROLES[Phase.IMPLEMENT],
            "Run `echo shelf-ok > ran.txt` and confirm it worked.",
            lambda _answer, root: (root / "ran.txt").exists(),
            "The sandbox cannot start on this host. Test it with `bwrap --ro-bind / / true`; if that fails set "
            "SHELF_SANDBOX_DISABLED=1 in deploy/.env (the container is then the only boundary around the agents).",
        ),
    ]


async def diagnose(agents: AgentBackend, model: str | None = None) -> list[Outcome]:
    """Run every check with ``agents`` in a fresh throwaway repository each."""
    outcomes: list[Outcome] = []
    for check in checks():
        with tempfile.TemporaryDirectory(prefix="shelf-doctor-") as directory:
            root = Path(directory)
            make_repository(root)
            task = AgentTask(
                check.role, check.system, check.prompt, root, max_turns=TURNS, max_budget_usd=BUDGET, model=model
            )
            try:
                answer = await asyncio.wait_for(agents.run(task), timeout=180)
            except Exception as error:  # noqa: BLE001 - the point is to report whatever went wrong
                outcomes.append(
                    Outcome(check.name, passed=False, detail=f"{type(error).__name__}: {error}"[:300], hint=check.hint)
                )
                continue
            ok = check.passes(answer, root)
            outcomes.append(
                Outcome(check.name, ok, "" if ok else f"answered: {answer.strip()[-200:]}", "" if ok else check.hint)
            )
    return outcomes


def report(outcomes: list[Outcome], *, credential: bool) -> str:
    """The result as a readable list, with what to do for each failure."""
    lines = [f"{'✓' if credential else '✗'} A model credential is set"]
    if not credential:
        lines.append(
            "    Run `claude setup-token` and set CLAUDE_CODE_OAUTH_TOKEN (or ANTHROPIC_API_KEY) in deploy/.env."
        )
    for outcome in outcomes:
        lines.append(f"{'✓' if outcome.passed else '✗'} {outcome.name}")
        if not outcome.passed:
            lines += [f"    {outcome.detail}", f"    -> {outcome.hint}"]
    return "\n".join(lines)


def main() -> None:
    """Console entry point: ``shelf-doctor``."""
    settings = settings_module.from_environ({"PUBLIC_URL": "http://doctor", "SESSION_SECRET": "doctor", **os.environ})
    backend = ClaudeBackend(
        nested_sandbox=settings.nested_sandbox, sandbox=settings.sandbox, cli_path=settings.claude_cli
    )
    outcomes = asyncio.run(diagnose(backend, settings.model))
    print(report(outcomes, credential=settings.model_credential))  # noqa: T201
    sys.exit(0 if settings.model_credential and all(outcome.passed for outcome in outcomes) else 1)


if __name__ == "__main__":
    main()
