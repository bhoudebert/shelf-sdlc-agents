"""Carrying out a step: a fresh clone, the role of the phase, and what comes out, read back as a result."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shelf.domain.config import RepoConfig
from shelf.domain.context import CATEGORIES, EARLIER_WORK, context_brief
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import Phase
from shelf.domain.roles import PROVIDED_DOCUMENT, REVIEWERS, ROLES, TITLER, documents_dir
from shelf.domain.story import agent_comment
from shelf.domain.titles import clean_title, fallback_title
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import Produced, RunStep, StepResult, Verified
from shelf.ports.agents import AgentBackend, AgentTask
from shelf.ports.configs import RepoConfigs
from shelf.ports.steps import PullRequests
from shelf.ports.workspace import Checkout, Workspace, Workspaces

TokenFor = Callable[[RepoRef], Awaitable[str]]
PromptFor = Callable[[str], str]
"""Gives the system prompt of a role, by name."""

TITLE_TURNS = 12
"""How many turns the agent that names the pull request may take."""

DOCUMENT_LIMIT = 20000
"""How much of a document is shown in its comment (the whole file is in the branch)."""

SUMMARY_LIMIT = 3000
"""How much of an agent's closing message is posted on the pull request."""

REPORT_TAIL = 4000
"""How much of a failing check's output goes back to the implementer."""


def branch_of(work: WorkContext) -> str:
    """The branch the work lives on."""
    return f"shelf/{work.id}"


def task_prompt(work: WorkContext, step: RunStep, base: str = "main", picture: str = "") -> str:
    """What the agent is asked, built from the request, the documents so far and the feedback that sent work back."""
    folder = documents_dir(work.id)
    role = ROLES[step.phase]
    lines = [
        f"Requested by: {work.request.requester}",
        f"Documents of this work live in `{folder}/` (spec.md, design.md, plan.md). Read the ones that exist.",
    ]
    if picture:
        lines += ["", picture]
    if work.request.text:
        lines += ["", "The request:", work.request.text]
    if step.feedback:
        lines += ["", f"This is round {step.attempt}. Address this feedback first:", step.feedback]
    if step.phase in REVIEWERS or role.name == "architect":
        lines += ["", f"The base branch is `{base}`: `git diff {base}...HEAD` shows what this work changed."]
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
        """Run ``step`` for ``work``, speak about it on the pull request as the agent it is, and read what came out."""
        repo = work.request.repo
        config = await self.configs.load(repo)
        token = await self.token_for(repo)
        reviewing = work.request.pull_request if step.phase is Phase.CODE_REVIEW else None
        checkout = Checkout(repo, token, branch_of(work), config.base_branch, reviewing)
        async with self.workspaces.open(checkout) as workspace:
            recorded = await self._record_request(work, workspace)
            result, speaker, words = await self._do(work, step, workspace, config, token)
            if recorded and not isinstance(result, Produced):
                await workspace.commit_and_push(f"chore(shelf): record the request for {work.id}")
            await self.pulls.comment(work, agent_comment(work.id, speaker, words))
            return result

    async def _do(
        self, work: WorkContext, step: RunStep, workspace: Workspace, config: RepoConfig, token: str
    ) -> tuple[StepResult, str, str]:
        """Carry out the phase; return its result, who speaks about it, and what they say."""
        if step.phase is Phase.VERIFY:
            checked, ran = await self._verify(workspace, config)
            return checked, "checks", ran
        answer = await self._ask_agent(work, step, workspace, token, config.base_branch)
        role = ROLES[step.phase]
        if step.phase in REVIEWERS:
            reviewed = parse_verdict(answer)
            return reviewed, role.name, f"**Verdict: {reviewed.verdict}**\n\n{reviewed.issues}".strip()
        await workspace.commit_and_push(f"chore(shelf): {role.name} for {work.id}")
        return Produced(), role.name, await self._story(work, step, workspace, config, answer)

    async def title(self, work: WorkContext) -> str:
        """The pull request's title by the repository's own convention; any failure falls back to the request."""
        fallback = fallback_title(work.request.text)
        repo = work.request.repo
        try:
            config = await self.configs.load(repo)
            token = await self.token_for(repo)
            async with self.workspaces.open(Checkout(repo, token, branch_of(work), config.base_branch)) as workspace:
                answer = await self.agents.run(
                    AgentTask(
                        role=TITLER,
                        system_prompt=self.prompt_for(TITLER.name),
                        prompt=self._title_prompt(work, config.base_branch, workspace),
                        workdir=workspace.path,
                        env={},
                        max_turns=TITLE_TURNS,
                        max_budget_usd=self.max_budget_usd,
                        model=self.model,
                    )
                )
        except Exception:  # noqa: BLE001 - a title is never worth stopping the work for
            return fallback
        return clean_title(answer, fallback)

    def _title_prompt(self, work: WorkContext, base: str, workspace: Workspace) -> str:
        lines = [
            f"Requested by: {work.request.requester}",
            (
                f"The base branch is `{base}`. What this work changes, ignoring the factory's own bookkeeping: "
                f"`git diff {base}...HEAD -- . ':(exclude)docs/shelf'`."
            ),
            (
                f"The documents of this work are in `{documents_dir(work.id)}/`: they record the request and the spec, "
                "and they are not what the pull request changes."
            ),
        ]
        if work.request.text:
            lines += ["", "The request:", work.request.text.strip()[:2000]]
        picture = self._picture(work, workspace)
        return "\n".join([*lines, "", picture] if picture else lines)

    async def _ask_agent(self, work: WorkContext, step: RunStep, workspace: Workspace, token: str, base: str) -> str:
        role = ROLES[step.phase]
        return await self.agents.run(
            AgentTask(
                role=role,
                system_prompt=self.prompt_for(role.name),
                prompt=task_prompt(work, step, base, self._picture(work, workspace)),
                workdir=workspace.path,
                env={"GH_TOKEN": token} if step.phase is Phase.IMPLEMENT else {},
                max_turns=self.max_turns,
                max_budget_usd=self.max_budget_usd,
                model=self.model,
            )
        )

    def _picture(self, work: WorkContext, workspace: Workspace) -> str:
        """Everything that already binds the repository (conventions, specs, decisions, earlier work), as a brief."""
        root = workspace.path
        found = {
            title: sorted({str(p.relative_to(root)) for pattern in patterns for p in root.glob(pattern) if p.is_file()})
            for title, patterns in CATEGORIES.items()
        }
        earlier = sorted(
            str(p.relative_to(root)) for p in root.glob(EARLIER_WORK) if p.is_file() and work.id not in p.parts
        )
        return context_brief(found, earlier)

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

    async def _story(
        self, work: WorkContext, step: RunStep, workspace: Workspace, config: RepoConfig, answer: str
    ) -> str:
        """What a producer says: its closing message, the document it wrote, and for the developer what changed."""
        role = ROLES[step.phase]
        parts = [f"Round {step.attempt}." if step.attempt else "", answer.strip()[:SUMMARY_LIMIT]]
        if role.document:
            path = f"{documents_dir(work.id)}/{role.document}"
            written = workspace.path / path
            if written.is_file():
                shown = written.read_text(encoding="utf-8")[:DOCUMENT_LIMIT]
                parts.append(f"<details><summary><code>{path}</code></summary>\n\n{shown}\n\n</details>")
        else:
            stat = await workspace.run(f"git diff --stat {config.base_branch}...HEAD")
            if stat.exit_code == 0 and stat.output.strip():
                parts.append(f"Changes:\n\n```\n{stat.output.strip()[:REPORT_TAIL]}\n```")
        return "\n\n".join(part for part in parts if part)

    async def _verify(self, workspace: Workspace, config: RepoConfig) -> tuple[Verified, str]:
        """Run the repository's checks; return the result for the machine and a report a person can read."""
        if not config.checks:
            note = "No checks configured for this repository."
            return Verified(passed=True, report=note), note
        failures: list[str] = []
        lines: list[str] = []
        for command in config.checks:
            result = await workspace.run(command)
            if result.exit_code == 0:
                lines.append(f"✅ `{command}`")
            else:
                lines.append(f"❌ `{command}` (exit {result.exit_code})")
                failures.append(f"$ {command} (exit {result.exit_code})\n{result.output[-REPORT_TAIL:]}")
        verified = Verified(passed=not failures, report="\n\n".join(failures))
        details = f"\n\n```\n{verified.report}\n```" if failures else ""
        return verified, f"**{'Passed' if verified.passed else 'Failed'}**\n\n" + "\n".join(lines) + details
