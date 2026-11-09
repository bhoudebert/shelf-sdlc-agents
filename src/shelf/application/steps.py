"""Carrying out a step: a fresh clone, the role of the phase, and what comes out, read back as a result."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from shelf.domain.ci import Ci, CiState
from shelf.domain.config import RepoConfig
from shelf.domain.context import CATEGORIES, EARLIER_WORK, context_brief
from shelf.domain.context_repo import FOLDER, note_for, parse_context
from shelf.domain.model import RepoRef, WorkContext
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.result import Err, Ok
from shelf.domain.roles import PROVIDED_DOCUMENT, REVIEWERS, ROLES, TITLER, documents_dir
from shelf.domain.story import agent_comment
from shelf.domain.titles import clean_title, fallback_title
from shelf.domain.toolchain import TOOLCHAIN_NOTE, toolchain_env
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import WAITING_FOR_CI, Produced, Reviewed, RunStep, StepResult, Verdict, Verified
from shelf.ports.agents import AgentBackend, AgentTask
from shelf.ports.configs import RepoConfigs
from shelf.ports.context_sources import ContextSources
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


def adopted_note(number: int | None, base: str) -> str:
    """What the developer is told about a pull request that already exists and whose branch it is working on."""
    return (
        f"This work is on pull request #{number}, which already exists. You are on its own branch, checked out in this "
        f"clone; the base branch is `{base}` (`git diff {base}...HEAD` shows the pull request). Do what the request "
        f"asks to that branch: you may rebase it onto the base (`git rebase origin/{base}`), amend, add commits and "
        "fix what breaks. You have no credentials and need none: you do not push, the system does, replacing the "
        "branch only if nobody pushed to it in the meantime. After a rebase, run the project's own checks. The "
        "repository's CI runs on what is pushed, and the checks wait for it."
    )


def task_prompt(  # noqa: PLR0913
    work: WorkContext,
    step: RunStep,
    base: str = "main",
    picture: str = "",
    *,
    toolchain: bool = False,
    ci: str = "",
    context: str = "",
) -> str:
    """What the agent is asked, built from the request, the documents so far and the feedback that sent work back."""
    folder = documents_dir(work.id)
    role = ROLES[step.phase]
    adopted = work.request.entry is EntryPoint.PULL_REQUEST_WORK
    lines = [f"Requested by: {work.request.requester}"]
    if adopted:
        lines += [adopted_note(work.request.pull_request, base)]
    else:
        lines += [
            f"Documents of this work live in `{folder}/` (spec.md, design.md, plan.md). Read the ones that exist."
        ]
    if picture:
        lines += ["", picture]
    if work.request.text:
        lines += ["", "The request:", work.request.text]
    if step.feedback:
        lines += ["", f"This is round {step.attempt}. Address this feedback first:", step.feedback]
    if step.phase in REVIEWERS or role.name == "architect":
        lines += ["", f"The base branch is `{base}`: `git diff {base}...HEAD` shows what this work changed."]
    sees_ci = step.phase in REVIEWERS or step.phase is Phase.IMPLEMENT
    notes = [
        f"What the repository's CI says about this pull request right now:\n{ci}" if ci and sees_ci else "",
        context,
        TOOLCHAIN_NOTE if toolchain else "",
    ]
    lines += [part for note in notes if note for part in ("", note)]
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
    base_path: str = ""
    """The ``PATH`` the agents start from; the tool shims are put in front of it."""
    cache_dir: str = ""
    """Where each repository's tools and package caches live; empty gives agents the worker's own home and no tools."""
    ci_wait: float = 1800.0
    """How long one checks step looks at the repository's CI before it hands the wait back to the workflow."""
    ci_poll: float = 60.0
    """Seconds between two looks at the CI."""
    ci_grace: float = 120.0
    """How long a commit may show no CI run at all before the repository counts as having none: runs appear a few
    seconds after a push, not at once."""
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    context_sources: ContextSources | None = None
    """Where other repositories are read from, as reference material put next to the clone (none without it)."""

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        """Run ``step`` for ``work``, speak about it on the pull request as the agent it is, and read what came out."""
        repo = work.request.repo
        config = await self.configs.load(repo)
        token = await self.token_for(repo)
        await self._straighten(work, step)
        reviewing = work.request.pull_request if step.phase is Phase.CODE_REVIEW else None
        branch, lease = await self._branch(work)
        checkout = Checkout(repo, token, branch, config.base_branch, reviewing, lease)
        async with self.workspaces.open(checkout) as workspace:
            await self._attach_context(work, workspace)
            recorded = await self._record_request(work, workspace)
            result, speaker, words = await self._do(work, step, workspace, config, token)
            if recorded and not isinstance(result, Produced):
                await workspace.commit_and_push(f"chore(shelf): record the request for {work.id}")
            if not _is_a_repeated_wait(step, result):
                await self.pulls.comment(work, agent_comment(work.id, speaker, words))
            return result

    async def _attach_context(self, work: WorkContext, workspace: Workspace) -> None:
        """Put read-only copies of the other repositories the work reads next to the clone, outside what git tracks.

        A repository that cannot be read stops the step with the reason: the agent was promised that reference.
        """
        if not work.request.context:
            return
        if self.context_sources is None:
            message = "this work reads other repositories, but this instance cannot read any"
            raise RuntimeError(message)
        git = workspace.path / ".git"
        if git.is_dir():
            exclude = git / "info" / "exclude"
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a", encoding="utf-8") as out:
                out.write(f"\n{FOLDER}/\n")
        for spec in work.request.context:
            match parse_context(spec):
                case Err(error):
                    raise RuntimeError(error)
                case Ok(item):
                    match await self.context_sources.copy_into(item, workspace.path / FOLDER / item.directory):
                        case Err(error):
                            message = f"cannot read {spec} as reference: {error}"
                            raise RuntimeError(message)
                        case Ok():
                            pass

    async def _straighten(self, work: WorkContext, step: RunStep) -> None:
        """Keep the pull request a straight line.

        A step that starts means the wait is over, and one that starts again because the flow circled back makes what
        came from that phase on outdated. Cosmetic: GitHub refusing it never stops the work.
        """
        if step.feedback == WAITING_FOR_CI:  # only another look at the CI: nothing moved
            return
        again = step.attempt > 0 or bool(step.feedback)
        try:
            await self.pulls.outdate(work, step.phase if again else None)
        except Exception:  # noqa: BLE001 - a tidy pull request is never worth stopping the work for
            return

    async def _branch(self, work: WorkContext) -> tuple[str, str]:
        """The branch a step works on, and for a pull request that is not ours where that branch is now.

        Work on someone's pull request changes that pull request's own branch, never a branch of ours, and only when the
        pull request is open and from this repository.
        """
        if work.request.entry is not EntryPoint.PULL_REQUEST_WORK:
            return branch_of(work), ""
        head = await self.pulls.head(work)
        if not head.same_repository:
            message = "this pull request comes from a fork: the App cannot push to its branch"
            raise RuntimeError(message)
        if not head.open:
            message = "this pull request is no longer open"
            raise RuntimeError(message)
        return head.branch, head.sha

    async def _do(
        self, work: WorkContext, step: RunStep, workspace: Workspace, config: RepoConfig, token: str
    ) -> tuple[StepResult, str, str]:
        """Carry out the phase; return its result, who speaks about it, and what they say."""
        if step.phase is Phase.VERIFY:
            checked, ran = await self._verify(work, step, workspace, config)
            return checked, "checks", ran
        sees_ci = step.phase in REVIEWERS or step.phase is Phase.IMPLEMENT
        ci = await self._ci_now(work) if sees_ci else Ci(CiState.NONE)
        prompt = task_prompt(
            work,
            step,
            config.base_branch,
            self._picture(work, workspace),
            toolchain=bool(self.cache_dir),
            ci=ci.report() if ci.state is not CiState.NONE else "",
            context=_context_note(work),
        )
        answer = await self._ask_agent(work, step, workspace, token, prompt)
        role = ROLES[step.phase]
        if step.phase in REVIEWERS:
            reviewed = hold_back_for_ci(parse_verdict(answer), ci)
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

    async def _ask_agent(self, work: WorkContext, step: RunStep, workspace: Workspace, token: str, prompt: str) -> str:
        role = ROLES[step.phase]
        return await self.agents.run(
            AgentTask(
                role=role,
                system_prompt=self.prompt_for(role.name),
                prompt=prompt,
                workdir=workspace.path,
                env={
                    **(self._toolchain_env(work, workspace)),
                    **({"GH_TOKEN": token} if step.phase is Phase.IMPLEMENT else {}),
                },
                max_turns=self.max_turns,
                max_budget_usd=self.max_budget_usd,
                model=self.model,
            )
        )

    def _toolchain_env(self, work: WorkContext, workspace: Workspace) -> dict[str, str]:
        """The repository's own home, caches and tool shims for this step (nothing when no cache directory is set)."""
        return toolchain_env(self.cache_dir, work.request.repo, str(workspace.path), self.base_path)

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

    async def _verify(
        self, work: WorkContext, step: RunStep, workspace: Workspace, config: RepoConfig
    ) -> tuple[Verified, str]:
        """Do what can be done here (the repository's commands), then rely on its CI for the rest."""
        lines: list[str] = []
        if step.feedback != WAITING_FOR_CI:
            local, lines = await self._local_checks(workspace, config)
            if not local.passed:  # no point waiting for a CI that will only repeat it
                return local, "**Failed**\n\n" + "\n".join(lines) + f"\n\n```\n{local.report}\n```"
        ci = await self._wait_for_ci(work)
        return _after_ci(ci, lines)

    async def _local_checks(self, workspace: Workspace, config: RepoConfig) -> tuple[Verified, list[str]]:
        """Run the repository's own commands; the lines say what each did."""
        if not config.checks:
            return Verified(passed=True), ["⚪ no commands configured for this repository (`checks` in its config)"]
        failures: list[str] = []
        lines: list[str] = []
        for command in config.checks:
            result = await workspace.run(command)
            if result.exit_code == 0:
                lines.append(f"✅ `{command}`")
            else:
                lines.append(f"❌ `{command}` (exit {result.exit_code})")
                failures.append(f"$ {command} (exit {result.exit_code})\n{result.output[-REPORT_TAIL:]}")
        return Verified(passed=not failures, report="\n\n".join(failures)), lines

    async def _ci_now(self, work: WorkContext) -> Ci:
        """The CI as it is; a CI that cannot be read counts as absent, and never stops a review."""
        try:
            return await self.pulls.ci(work)
        except Exception:  # noqa: BLE001 - GitHub being unreachable is not a verdict on the work
            return Ci(CiState.NONE)

    async def _wait_for_ci(self, work: WorkContext) -> Ci:
        """Look at the CI until it settles or this step's share of the wait is used up."""
        waited = 0.0
        while True:
            ci = await self._ci_now(work)
            if ci.state is CiState.NONE:
                if waited >= self.ci_grace:
                    return ci
            elif ci.settled and ci.state is not CiState.BLOCKED:
                return ci
            if waited >= self.ci_wait:
                return ci
            await self.sleep(self.ci_poll)
            waited += self.ci_poll


def _is_a_repeated_wait(step: RunStep, result: StepResult) -> bool:
    """Whether this is one more look at a CI that was already reported as running: nothing new to say."""
    return step.feedback == WAITING_FOR_CI and isinstance(result, Verified) and result.waiting


def _after_ci(ci: Ci, local_lines: list[str]) -> tuple[Verified, str]:
    """What the checks conclude from the CI, and the report a person reads."""
    lines = [*local_lines, *_ci_line(ci)]
    body = "\n".join(lines)
    match ci.state:
        case CiState.RED:
            return Verified(passed=False, report=ci.report()), f"**Failed**\n\n{body}\n\n```\n{ci.report()}\n```"
        case CiState.PENDING | CiState.BLOCKED:
            return Verified(passed=False, report=ci.report(), waiting=True), f"**Waiting for CI**\n\n{body}"
        case CiState.GREEN | CiState.NONE:
            return Verified(passed=True), f"**Passed**\n\n{body}"


def _ci_line(ci: Ci) -> list[str]:
    match ci.state:
        case CiState.NONE:
            return ["⚪ no CI run found on the pull request"]
        case CiState.GREEN:
            return [f"✅ CI: {len(ci.runs)} runs, all green"]
        case CiState.RED:
            return [f"❌ CI: {', '.join(run.name for run in ci.failing)}"]
        case CiState.PENDING:
            return ["⏳ CI is still running"]
        case CiState.BLOCKED:
            return ["⏸ CI waits for someone to approve a run on GitHub"]


def hold_back_for_ci(reviewed: Reviewed, ci: Ci) -> Reviewed:
    """A reviewer cannot approve over a CI that is red (changes) or not finished (a person decides)."""
    if reviewed.verdict is not Verdict.APPROVE:
        return reviewed
    match ci.state:
        case CiState.RED:
            return Reviewed(
                Verdict.CHANGES, f"{reviewed.issues}\n\nNot approved: the CI is red.\n{ci.report()}".strip()
            )
        case CiState.PENDING | CiState.BLOCKED:
            return Reviewed(
                Verdict.ESCALATE,
                f"{reviewed.issues}\n\nNot approved yet: the CI has not finished.\n{ci.report()}".strip(),
            )
        case CiState.GREEN | CiState.NONE:
            return reviewed


def _context_note(work: WorkContext) -> str:
    """What the agent is told about the reference repositories of this work, nothing when it has none."""
    found = [parse_context(spec) for spec in work.request.context]
    return note_for(tuple(item.value for item in found if isinstance(item, Ok))) if work.request.context else ""
