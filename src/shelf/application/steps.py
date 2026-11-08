"""Carrying out a step: a fresh clone, the role of the phase, and what comes out, read back as a result."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shelf.domain.config import RepoConfig
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import Phase
from shelf.domain.roles import PROVIDED_DOCUMENT, REVIEWERS, ROLES, documents_dir
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import Produced, RunStep, StepResult, Verified
from shelf.ports.agents import AgentBackend, AgentTask
from shelf.ports.configs import RepoConfigs
from shelf.ports.steps import PullRequests
from shelf.ports.workspace import Checkout, Workspace, Workspaces

TokenFor = Callable[[RepoRef], Awaitable[str]]
PromptFor = Callable[[str], str]
"""Gives the system prompt of a role, by name."""

SUMMARY_LIMIT = 3000
"""How much of an agent's closing message is posted on the pull request."""

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
        """Run ``step`` for ``work``, say what happened on the pull request, and read what came out."""
        repo = work.request.repo
        config = await self.configs.load(repo)
        token = await self.token_for(repo)
        reviewing = work.request.pull_request if step.phase is Phase.CODE_REVIEW else None
        checkout = Checkout(repo, token, branch_of(work), config.base_branch, reviewing)
        async with self.workspaces.open(checkout) as workspace:
            recorded = await self._record_request(work, workspace)
            result, report = await self._do(work, step, workspace, config, token)
            if recorded and not isinstance(result, Produced):
                await workspace.commit_and_push(f"chore(shelf): record the request for {work.id}")
            await self._report(work, report)
            return result

    async def _do(
        self, work: WorkContext, step: RunStep, workspace: Workspace, config: RepoConfig, token: str
    ) -> tuple[StepResult, str]:
        """Carry out the phase and return its result with the text to post about it."""
        if step.phase is Phase.VERIFY:
            checked = await self._verify(workspace, config)
            return checked, f"**Checks: {'passed' if checked.passed else 'failed'}**\n\n{checked.report}".strip()
        answer = await self._ask_agent(work, step, workspace, token)
        if step.phase in REVIEWERS:
            reviewed = parse_verdict(answer)
            return reviewed, f"**{ROLES[step.phase].name}: {reviewed.verdict}**\n\n{reviewed.issues}".strip()
        await workspace.commit_and_push(f"chore(shelf): {ROLES[step.phase].name} for {work.id}")
        return Produced(), self._summary(work, step, answer)

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

    async def _record_request(self, work: WorkContext, workspace: Workspace) -> bool:
        """Write the text the person submitted into the repository, once, so everyone reads the same document."""
        name = PROVIDED_DOCUMENT.get(work.request.entry)
        if name is None or not work.request.text.strip():
            return False
        target = workspace.path / documents_dir(work.id) / name
        if target.exists():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(work.request.text.rstrip() + "\n", encoding="utf-8")
        return True

    async def _report(self, work: WorkContext, body: str) -> None:
        """Say what a step did on the pull request, if it is open yet."""
        await self.pulls.comment(work, body)

    def _summary(self, work: WorkContext, step: RunStep, answer: str) -> str:
        role = ROLES[step.phase]
        files = f"\n\nFile: `{documents_dir(work.id)}/{role.document}`" if role.document else ""
        text = answer.strip()[:SUMMARY_LIMIT]
        return f"**{role.name}** finished (round {step.attempt}).{files}\n\n{text}".strip()

    async def _verify(self, workspace: Workspace, config: RepoConfig) -> Verified:
        if not config.checks:
            return Verified(passed=True, report="No checks configured for this repository.")
        failures: list[str] = []
        for command in config.checks:
            result = await workspace.run(command)
            if result.exit_code != 0:
                failures.append(f"$ {command} (exit {result.exit_code})\n{result.output[-REPORT_TAIL:]}")
        return Verified(passed=not failures, report="\n\n".join(failures))
