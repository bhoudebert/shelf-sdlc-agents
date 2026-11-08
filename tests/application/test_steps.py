import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from shelf.application.steps import Steps, branch_of, task_prompt
from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.story import agent_comment
from shelf.domain.work import Produced, Reviewed, RunStep, Verdict, Verified
from shelf.ports.agents import AgentTask
from shelf.ports.workspace import Checkout, CheckResult
from tests.adapters.temporal.test_workflow import FakePulls
from tests.fakes import FakeConfigs

REPO = RepoRef("acme", "shop")
NEED = WorkContext(WorkId("work-1"), WorkRequest(REPO, "alice", EntryPoint.NEED, "loyalty points"))
REVIEW = WorkContext(WorkId("work-2"), WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, pull_request=7))


@dataclass
class FakeWorkspace:
    path: Path = field(default_factory=lambda: Path(tempfile.mkdtemp()))
    commands: dict[str, int] = field(default_factory=dict[str, int])
    ran: list[str] = field(default_factory=list[str])
    pushed: list[str] = field(default_factory=list[str])

    async def run(self, command: str) -> CheckResult:
        self.ran.append(command)
        code = self.commands.get(command, 0)
        return CheckResult(command, code, f"output of {command}")

    async def commit_and_push(self, message: str) -> bool:
        self.pushed.append(message)
        return True


@dataclass
class FakeWorkspaces:
    workspace: FakeWorkspace = field(default_factory=FakeWorkspace)
    opened: list[Checkout] = field(default_factory=list[Checkout])

    @asynccontextmanager
    async def open(self, checkout: Checkout) -> AsyncGenerator[FakeWorkspace]:
        self.opened.append(checkout)
        yield self.workspace


@dataclass
class FakeAgents:
    answer: str = "done"
    tasks: list[AgentTask] = field(default_factory=list[AgentTask])

    async def run(self, task: AgentTask) -> str:
        self.tasks.append(task)
        return self.answer


async def token_for(repo: RepoRef) -> str:
    return "ghs_token"


def steps(
    agents: FakeAgents | None = None,
    workspaces: FakeWorkspaces | None = None,
    pulls: FakePulls | None = None,
    config: RepoConfig | None = None,
) -> Steps:
    return Steps(
        workspaces=workspaces or FakeWorkspaces(),
        agents=agents or FakeAgents(),
        configs=FakeConfigs({REPO: config} if config else {}),
        pulls=pulls or FakePulls(),
        token_for=token_for,
        prompt_for=lambda role: f"prompt of {role}",
        model="a-model",
        max_budget_usd=2.0,
    )


async def test_a_producer_runs_its_role_in_a_clone_and_pushes_what_it_wrote() -> None:
    agents, workspaces = FakeAgents(), FakeWorkspaces()
    result = await steps(agents, workspaces).run(NEED, RunStep(Phase.INTAKE, 0, ""))
    assert result == Produced()
    [task] = agents.tasks
    assert task.role.name == "intake"
    assert task.system_prompt == "prompt of intake"
    assert task.env == {"GH_TOKEN": "ghs_token"}
    assert (task.model, task.max_budget_usd) == ("a-model", 2.0)
    assert workspaces.opened == [Checkout(REPO, "ghs_token", "shelf/work-1", "main", None)]
    assert workspaces.workspace.pushed == ["chore(shelf): intake for work-1"]


async def test_a_reviewer_reads_the_verdict_and_pushes_nothing() -> None:
    workspaces = FakeWorkspaces()
    result = await steps(FakeAgents("Too vague.\nVERDICT: CHANGES"), workspaces).run(
        NEED, RunStep(Phase.SPEC_REVIEW, 0, "")
    )
    assert result == Reviewed(Verdict.CHANGES, "Too vague.")
    assert workspaces.workspace.pushed == ["chore(shelf): record the request for work-1"]


async def test_the_code_review_of_a_pull_request_is_posted_on_it_and_reads_its_head() -> None:
    pulls, workspaces = FakePulls(), FakeWorkspaces()
    result = await steps(FakeAgents("Rename it.\nVERDICT: CHANGES"), workspaces, pulls).run(
        REVIEW, RunStep(Phase.CODE_REVIEW, 0, "")
    )
    assert result == Reviewed(Verdict.CHANGES, "Rename it.")
    assert pulls.commented == [agent_comment("work-2", "code_reviewer", "**Verdict: changes**\n\nRename it.")]
    assert workspaces.opened[0].pull_request == 7


async def test_the_checks_pass_when_every_command_exits_zero() -> None:
    workspaces = FakeWorkspaces()
    config = RepoConfig(checks=("make lint", "make test"))
    result = await steps(workspaces=workspaces, config=config).run(NEED, RunStep(Phase.VERIFY, 0, ""))
    assert result == Verified(passed=True)
    assert workspaces.workspace.ran == ["make lint", "make test"]


async def test_failing_checks_report_each_failure_for_the_implementer() -> None:
    workspaces = FakeWorkspaces(FakeWorkspace(commands={"make test": 2}))
    config = RepoConfig(checks=("make lint", "make test"))
    result = await steps(workspaces=workspaces, config=config).run(NEED, RunStep(Phase.VERIFY, 0, ""))
    assert isinstance(result, Verified)
    assert not result.passed
    assert "$ make test (exit 2)" in result.report
    assert "make lint" not in result.report


async def test_a_repository_without_checks_passes_verification_and_says_so() -> None:
    result = await steps().run(NEED, RunStep(Phase.VERIFY, 0, ""))
    assert result == Verified(passed=True, report="No checks configured for this repository.")


def test_the_task_prompt_carries_the_request_the_feedback_and_where_to_write() -> None:
    prompt = task_prompt(NEED, RunStep(Phase.INTAKE, 2, "add limits"))
    assert "Requested by: alice" in prompt
    assert "loyalty points" in prompt
    assert "round 2" in prompt
    assert "add limits" in prompt
    assert "docs/shelf/work-1/spec.md" in prompt


def test_a_reviewers_prompt_asks_for_a_verdict_line() -> None:
    assert "VERDICT: APPROVE" in task_prompt(NEED, RunStep(Phase.SPEC_REVIEW, 0, ""))
    assert "VERDICT" not in task_prompt(NEED, RunStep(Phase.IMPLEMENT, 0, ""))


def test_the_branch_belongs_to_the_work() -> None:
    assert branch_of(NEED) == "shelf/work-1"


async def test_the_submitted_text_is_recorded_in_the_repository_for_everyone_to_read() -> None:
    workspaces = FakeWorkspaces()
    await steps(workspaces=workspaces).run(NEED, RunStep(Phase.INTAKE, 0, ""))
    recorded = workspaces.workspace.path / "docs/shelf/work-1/request.md"
    assert recorded.read_text() == "loyalty points\n"


async def test_a_submitted_spec_is_recorded_as_the_spec_the_reviewers_read() -> None:
    workspaces = FakeWorkspaces()
    work = WorkContext(WorkId("work-3"), WorkRequest(REPO, "alice", EntryPoint.SPEC, "The system SHALL..."))
    await steps(workspaces=workspaces).run(work, RunStep(Phase.SPEC_REVIEW, 0, ""))
    assert (workspaces.workspace.path / "docs/shelf/work-3/spec.md").read_text() == "The system SHALL...\n"
    assert workspaces.workspace.pushed == ["chore(shelf): record the request for work-3"]


async def test_the_recorded_request_is_never_overwritten_by_a_later_step() -> None:
    workspaces = FakeWorkspaces()
    target = workspaces.workspace.path / "docs/shelf/work-1/request.md"
    target.parent.mkdir(parents=True)
    target.write_text("edited by a person\n")
    await steps(workspaces=workspaces).run(NEED, RunStep(Phase.INTAKE, 1, "more"))
    assert target.read_text() == "edited by a person\n"


async def test_a_producer_speaks_as_itself_and_shows_the_document_it_wrote() -> None:
    pulls, workspaces = FakePulls(), FakeWorkspaces()
    written = workspaces.workspace.path / "docs/shelf/work-1/spec.md"
    written.parent.mkdir(parents=True)
    written.write_text("# Spec\n\nThe system SHALL earn points.\n")
    await steps(FakeAgents("Wrote 3 requirements."), workspaces, pulls).run(NEED, RunStep(Phase.INTAKE, 0, ""))
    [comment] = pulls.commented
    assert comment.startswith("<!-- shelf-agent:intake:work-1 -->\n**Spec writer** · agent")
    assert "Wrote 3 requirements." in comment
    assert "<details><summary><code>docs/shelf/work-1/spec.md</code></summary>" in comment
    assert "The system SHALL earn points." in comment


async def test_the_developer_says_what_changed() -> None:
    pulls = FakePulls()
    workspaces = FakeWorkspaces(FakeWorkspace(commands={"git diff --stat main...HEAD": 0}))
    await steps(FakeAgents("Implemented the points."), workspaces, pulls).run(NEED, RunStep(Phase.IMPLEMENT, 1, "fix"))
    [comment] = pulls.commented
    assert "**Developer** · agent" in comment
    assert "Round 1." in comment
    assert "Changes:" in comment
    assert "output of git diff --stat main...HEAD" in comment


async def test_every_review_and_check_is_reported_as_the_agent_that_made_it() -> None:
    pulls = FakePulls()
    runner = steps(FakeAgents("Too vague.\nVERDICT: CHANGES"), pulls=pulls, config=RepoConfig(checks=("make test",)))
    await runner.run(NEED, RunStep(Phase.SPEC_REVIEW, 0, ""))
    await runner.run(NEED, RunStep(Phase.VERIFY, 0, ""))
    first, second = pulls.commented
    assert first == agent_comment("work-1", "spec_critic", "**Verdict: changes**\n\nToo vague.")
    assert second.startswith("<!-- shelf-agent:checks:work-1 -->\n**Checks** · agent")
    assert "✅ `make test`" in second
    assert "**Passed**" in second


async def test_failing_checks_are_listed_with_their_output_for_everyone_to_read() -> None:
    pulls = FakePulls()
    workspaces = FakeWorkspaces(FakeWorkspace(commands={"make test": 2}))
    await steps(workspaces=workspaces, pulls=pulls, config=RepoConfig(checks=("make lint", "make test"))).run(
        NEED, RunStep(Phase.VERIFY, 0, "")
    )
    [comment] = pulls.commented
    assert "**Failed**" in comment
    assert "✅ `make lint`" in comment
    assert "❌ `make test` (exit 2)" in comment
    assert "output of make test" in comment
