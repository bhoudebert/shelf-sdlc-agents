import subprocess  # noqa: TC003 - used at run time by the tests below
from collections.abc import Callable
from pathlib import Path

import pytest

from shelf.entrypoints.doctor import CONVENTIONAL, Outcome, checks, diagnose, report, title_of
from shelf.ports.agents import AgentTask


class Scripted:
    """An agent backend that answers each check from a table and can do what a real agent would do in the repository."""

    def __init__(self, answers: dict[str, str], *, runs_commands: bool = True) -> None:
        self.answers, self.runs_commands = answers, runs_commands

    async def run(self, task: AgentTask) -> str:
        if self.runs_commands and "echo shelf-ok" in task.prompt:
            (task.workdir / "ran.txt").write_text("shelf-ok\n")
        for needle, answer in self.answers.items():
            if needle in task.prompt:
                return answer
        return ""


GOOD = {
    "git log": "The newest commit is: fix(core): second commit",
    "Say hello": "Hello! PINEAPPLE",
    "pull request title": "fix(readme): correct a typo",
    "echo shelf-ok": "done",
}


async def test_a_healthy_instance_passes_every_check() -> None:
    outcomes = await diagnose(Scripted(GOOD))
    assert all(o.passed for o in outcomes), [o for o in outcomes if not o.passed]
    assert len(outcomes) == len(checks())


async def test_agents_that_ignore_themake_repositorys_claude_md_are_reported() -> None:
    outcomes = await diagnose(Scripted({**GOOD, "Say hello": "Hello!"}))
    failed = [o for o in outcomes if not o.passed]
    assert [o.name for o in failed] == ["The repository's own CLAUDE.md is loaded"]
    assert "CLAUDE.md" in failed[0].hint


async def test_a_sandbox_that_cannot_run_commands_is_reported_with_the_way_out() -> None:
    outcomes = await diagnose(Scripted(GOOD, runs_commands=False))
    failed = [o for o in outcomes if not o.passed]
    assert [o.name for o in failed] == ["The developer can run commands"]
    assert "SHELF_SANDBOX_DISABLED" in failed[0].hint


async def test_a_title_outside_themake_repositorys_convention_is_reported() -> None:
    outcomes = await diagnose(Scripted({**GOOD, "pull request title": "Let's add a typo fix"}))
    assert [o.name for o in outcomes if not o.passed] == [
        "The agent that names pull requests follows the repository's convention"
    ]


async def test_an_agent_that_crashes_is_reported_not_raised() -> None:
    class Crashing:
        async def run(self, task: AgentTask) -> str:
            message = "Not logged in"
            raise RuntimeError(message)

    outcomes = await diagnose(Crashing())
    assert all(not o.passed for o in outcomes)
    assert "Not logged in" in outcomes[0].detail


def test_the_report_marks_each_check_and_says_what_to_do_about_a_failure() -> None:
    text = report(
        [Outcome("A", passed=True, detail=""), Outcome("B", passed=False, detail="boom", hint="do this")],
        credential=True,
    )
    assert "✓ A" in text
    assert "✗ B" in text
    assert "-> do this" in text


def test_a_missing_credential_is_the_first_thing_reported() -> None:
    assert report([], credential=False).startswith("✗ A model credential is set")


@pytest.mark.parametrize("title", ["feat: x", "fix(api): y", "docs(readme)!: z", "chore(deps): bump"])
def test_the_conventional_title_pattern_accepts_the_usual_forms(title: str) -> None:
    assert CONVENTIONAL.match(title)


@pytest.mark.parametrize("title", ["Add badges", "feat:", "Feat: x", "feature: x"])
def test_and_refuses_the_rest(title: str) -> None:
    assert not CONVENTIONAL.match(title)


def test_every_check_is_run_in_amake_repository_that_has_history_a_rule_file_and_a_convention(tmp_path: Path) -> None:
    from shelf.entrypoints.doctor import make_repository  # noqa: PLC0415

    make_repository(tmp_path)
    assert (tmp_path / "CLAUDE.md").read_text().startswith("CLAUDE-MD-RULE")
    assert (tmp_path / ".git").is_dir()


def fake_run(done: "subprocess.CompletedProcess[str]") -> Callable[..., "subprocess.CompletedProcess[str]"]:
    def run(*_args: object, **_kwargs: object) -> "subprocess.CompletedProcess[str]":
        return done

    return run


def test_a_sandbox_that_starts_is_reported_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess  # noqa: PLC0415

    from shelf.entrypoints import doctor  # noqa: PLC0415

    monkeypatch.setattr(doctor.subprocess, "run", fake_run(subprocess.CompletedProcess([], 0, "", "")))
    assert doctor.probe_sandbox().passed


def test_a_sandbox_that_cannot_start_says_what_bubblewrap_said_and_how_to_fix_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess  # noqa: PLC0415

    from shelf.entrypoints import doctor  # noqa: PLC0415

    failed = subprocess.CompletedProcess([], 1, "", "bwrap: No permissions to create new namespace")
    monkeypatch.setattr(doctor.subprocess, "run", fake_run(failed))
    outcome = doctor.probe_sandbox()
    assert not outcome.passed
    assert "No permissions to create new namespace" in outcome.detail
    assert "sh deploy/fix-ubuntu.sh" in outcome.hint
    assert "can read the worker's environment" in outcome.hint


async def test_the_sandbox_probe_comes_first_and_is_skipped_when_the_sandbox_is_off() -> None:
    probed = await diagnose(Scripted(GOOD), sandbox=lambda: Outcome("The sandbox can start", passed=True, detail=""))
    assert probed[0].name == "The sandbox can start"
    assert (await diagnose(Scripted(GOOD)))[0].name != "The sandbox can start"


def test_the_title_is_the_first_line_even_when_a_repository_rule_adds_a_closing_word() -> None:
    assert title_of("docs(core): fix typo in README\n\nPINEAPPLE") == "docs(core): fix typo in README"
    assert title_of("`fix(web): a`") == "fix(web): a"
    assert title_of("") == ""
