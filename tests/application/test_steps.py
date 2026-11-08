from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

from shelf.application.steps import Steps, branch_of, task_prompt
from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkContext, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
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
    path: Path = Path("/clone")
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
    assert workspaces.workspace.pushed == []


async def test_the_code_review_of_a_pull_request_is_posted_on_it_and_reads_its_head() -> None:
    pulls, workspaces = FakePulls(), FakeWorkspaces()
    result = await steps(FakeAgents("Rename it.\nVERDICT: CHANGES"), workspaces, pulls).run(
        REVIEW, RunStep(Phase.CODE_REVIEW, 0, "")
    )
    assert result == Reviewed(Verdict.CHANGES, "Rename it.")
    assert pulls.commented == ["**Review (changes)**\n\nRename it."]
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
