"""Carrying out a step: a fresh clone, the role of the phase, and what comes out, read back as a result."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import Phase
from shelf.domain.roles import REVIEWERS, ROLES, documents_dir
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import Produced, RunStep, StepResult, Verified
from shelf.ports.agents import AgentBackend, AgentTask
from shelf.ports.configs import RepoConfigs
from shelf.ports.steps import PullRequests
from shelf.ports.workspace import Checkout, Workspace, Workspaces

TokenFor = Callable[[RepoRef], Awaitable[str]]
PromptFor = Callable[[str], str]
"""Gives the system prompt of a role, by name."""

REPORT_TAIL = 4000
"""How much of a failing check's output goes back to the implementer."""


def branch_of(work: WorkContext) -> str:
    """The branch the work lives on."""
    return f"shelf/{work.id}"


def task_prompt(work: WorkContext, step: RunStep) -> str:
    """What the agent is asked, built from the request, the documents so far and the feedback that sent work back."""
    folder = documents_dir(work.id)
    role = ROLES[step.phase]
    lines = [
        f"Requested by: {work.request.requester}",
        f"Documents of this work live in `{folder}/` (spec.md, design.md, plan.md). Read the ones that exist.",
    ]
    if work.request.text:
        lines += ["", "The request:", work.request.text]
    if step.feedback:
        lines += ["", f"This is round {step.attempt}. Address this feedback first:", step.feedback]
    if role.document:
        lines += ["", f"Write your result to `{folder}/{role.document}`."]
    if step.phase in REVIEWERS:
        lines += [
            "",
            "End your answer with a single line `VERDICT: APPROVE`, `VERDICT: CHANGES` or `VERDICT: ESCALATE`.",
        ]
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Steps:
    """The ``StepRunner`` port: one clone per step, one role per phase, the project's checks for verification."""

    workspaces: Workspaces
    agents: AgentBackend
    configs: RepoConfigs
    pulls: PullRequests
    token_for: TokenFor
    prompt_for: PromptFor
    model: str | None = None
    max_turns: int = 40
    max_budget_usd: float | None = None

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        """Run ``step`` for ``work`` and read what came out."""
        repo = work.request.repo
        config = await self.configs.load(repo)
        token = await self.token_for(repo)
        reviewing = work.request.pull_request if step.phase is Phase.CODE_REVIEW else None
        checkout = Checkout(repo, token, branch_of(work), config.base_branch, reviewing)
        async with self.workspaces.open(checkout) as workspace:
            if step.phase is Phase.VERIFY:
                return await self._verify(workspace, config)
            answer = await self._ask_agent(work, step, workspace, token)
            if step.phase in REVIEWERS:
                return await self._review(work, step, answer)
            await workspace.commit_and_push(f"chore(shelf): {ROLES[step.phase].name} for {work.id}")
            return Produced()

    async def _ask_agent(self, work: WorkContext, step: RunStep, workspace: Workspace, token: str) -> str:
        role = ROLES[step.phase]
        return await self.agents.run(
            AgentTask(
                role=role,
                system_prompt=self.prompt_for(role.name),
                prompt=task_prompt(work, step),
                workdir=workspace.path,
                env={"GH_TOKEN": token},
                max_turns=self.max_turns,
                max_budget_usd=self.max_budget_usd,
                model=self.model,
            )
        )

    async def _review(self, work: WorkContext, step: RunStep, answer: str) -> StepResult:
        reviewed = parse_verdict(answer)
        if step.phase is Phase.CODE_REVIEW and work.request.pull_request is not None:
            await self.pulls.comment(work, f"**Review ({reviewed.verdict})**\n\n{reviewed.issues}")
        return reviewed

    async def _verify(self, workspace: Workspace, config: RepoConfig) -> Verified:
        if not config.checks:
            return Verified(passed=True, report="No checks configured for this repository.")
        failures: list[str] = []
        for command in config.checks:
            result = await workspace.run(command)
            if result.exit_code != 0:
                failures.append(f"$ {command} (exit {result.exit_code})\n{result.output[-REPORT_TAIL:]}")
        return Verified(passed=not failures, report="\n\n".join(failures))
