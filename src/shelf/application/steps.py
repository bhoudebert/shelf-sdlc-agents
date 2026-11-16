"""Carrying out a step: a fresh clone, the role of the phase, and what comes out, read back as a result."""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

from shelf.domain.ci import Ci, CiState
from shelf.domain.config import InvalidConfigError, RepoConfig
from shelf.domain.context import CATEGORIES, EARLIER_WORK, context_brief
from shelf.domain.context_repo import FOLDER, note_for, parse_context
from shelf.domain.decisions import FILE as DECISIONS_FILE
from shelf.domain.decisions import DecisionRecord, acted_as, append_entry
from shelf.domain.formatters import (
    IGNORE_FILE,
    READ,
    SANDBOX_NOTE,
    prettier_ignore,
    uses_prettier,
    with_sandbox_placeholders,
    without_sandbox_placeholders,
)
from shelf.domain.mise_config import declared_tools, ignored_sections
from shelf.domain.model import RepoRef, WorkContext, WorkId
from shelf.domain.nix import (
    TIME_LIMIT,
    ci_uses_nix,
    dev_environment,
    has_flake,
    nix_failed,
    nix_ready,
    print_dev_env_command,
)
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.result import Err, Ok
from shelf.domain.results import Results, results_note
from shelf.domain.review import ReviewDepth, review_note
from shelf.domain.roles import (
    PROVIDED_DOCUMENT,
    REVIEWERS,
    ROLES,
    TITLER,
    AgentRole,
    documents_dir,
    legacy_documents_dir,
)
from shelf.domain.runlog import RunRecord, keep_events, redact
from shelf.domain.story import agent_comment
from shelf.domain.titles import clean_title, fallback_title
from shelf.domain.tool_detection import DECLARED, SOURCES, detect_tools, is_declared
from shelf.domain.toolchain import (
    TOOLCHAIN_NOTE,
    declared_failed,
    declared_ready,
    dependencies_command,
    dependencies_failed,
    dependencies_ready,
    nothing_to_install,
    setup_command,
    toolchain_env,
    tools_failed,
    tools_ready,
    with_environment,
)
from shelf.domain.usage import Usage
from shelf.domain.verdict import parse_verdict
from shelf.domain.web import WEB_NOTE
from shelf.domain.work import WAITING_FOR_CI, Produced, Reviewed, RunStep, StepResult, Verdict, Verified
from shelf.ports.agents import AgentBackend, AgentTask, RunSink
from shelf.ports.configs import RepoConfigs
from shelf.ports.context_sources import ContextSources
from shelf.ports.run_records import RunRecords
from shelf.ports.steps import PullRequests
from shelf.ports.workspace import Checkout, Workspace, Workspaces

log = logging.getLogger(__name__)

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


UNATTENDED_NOTE = (
    "Nobody is available to answer while this work runs, and it goes on past a spec or design review that cannot "
    "settle. Do not stop to ask: where the request leaves a choice open, take the most reasonable reading and write "
    "each such choice under an `Assumptions` heading of your document, so a person can check them afterwards. A "
    "reviewer states plainly any point it cannot settle: it is handed to the person with the pull request."
)


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


def _depth_for(work: WorkContext, phase: Phase, config: RepoConfig) -> ReviewDepth:
    """How deep this review looks: what was chosen for the work, else the repository's file."""
    chosen = work.request.autonomy
    if phase is Phase.SPEC_REVIEW:
        return (chosen and chosen.spec_review_depth) or config.policy.spec_review_depth
    return (chosen and chosen.design_review_depth) or config.policy.design_review_depth


CI_PHASES = frozenset({Phase.IMPLEMENT, Phase.CODE_REVIEW})
"""The steps that are told what the CI says: the code. A spec or a design is not judged by the checks of a draft."""


DOCUMENT_FORMAT_NOTE = (
    "The document is committed to the repository. The system keeps Prettier off this folder, so a formatting check "
    "over the whole repository does not cover it. If the repository has another formatter or linter that you can run "
    "on a markdown file with what you have here, run it on your file; if you cannot run one, do not spend turns "
    "installing it: say so in one line."
)

SYSTEM_FILES_NOTE = (
    "The work's folder under `.shelf/` (the request, the spec, the design, the plan, the decision log) is part of the "
    "pull request on purpose: the system commits it. The `.shelf/` line it adds to a repository's `.prettierignore` is "
    "the system's too. Do not ask to remove them, do not write that they stay out of the pull request, and do not "
    "judge them as a change to the repository."
)

NOTHING_VERIFIED = (
    "⚪ nothing was verified here: no commands configured for this repository. Set `checks` in `.shelf/config.toml` on "
    'its default branch, for example `checks = ["mise run check"]` with a `[tasks.check]` in `mise.toml` that builds '
    "and tests the project, whatever its language; the tools come from `mise.toml` (or the flake)."
)

TOOL_PHASES = frozenset({Phase.IMPLEMENT, Phase.CODE_REVIEW})
"""The steps that build and test, and so need the repository's tools."""

SETUP_TIMEOUT = 600.0
"""Seconds the worker gives the installation of a repository's tools."""

MAX_SOURCE = 200_000
"""The most of one file the detection reads."""


def _read_sources(root: Path) -> dict[str, str]:
    """The files the versions are read from, and the ones that say a repository declares its tools."""
    found: dict[str, str] = {}
    for pattern in (*SOURCES, *DECLARED):
        for path in root.glob(pattern):
            if path.is_file() and path.stat().st_size <= MAX_SOURCE:
                found[str(path.relative_to(root))] = path.read_text(encoding="utf-8", errors="replace")
    return found


@dataclass(frozen=True, slots=True)
class ToolSetup:
    """What the worker made available before an agent starts: what to tell it, and what to add to its environment."""

    note: str = ""
    env: Mapping[str, str] = field(default_factory=dict[str, str])


def _keep_out_of_the_formatter(root: Path) -> None:
    """Make a repository that uses Prettier ignore Shelf's own files: it never has to download or run anything."""
    files = {
        name: (root / name).read_text(encoding="utf-8", errors="replace") for name in READ if (root / name).is_file()
    }
    updated = prettier_ignore(files)
    if updated is not None:
        (root / IGNORE_FILE).write_text(updated, encoding="utf-8")


def _uses_prettier(root: Path) -> bool:
    files = {
        name: (root / name).read_text(encoding="utf-8", errors="replace") for name in READ if (root / name).is_file()
    }
    return uses_prettier(files)


def _hide_sandbox_placeholders(root: Path) -> bool:
    """For a repository that uses Prettier, make its ignore file skip the sandbox's placeholders; whether it did."""
    if not _uses_prettier(root):
        return False
    path = root / IGNORE_FILE
    existing = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
    path.write_text(with_sandbox_placeholders(existing), encoding="utf-8")
    return True


def _show_sandbox_placeholders_again(root: Path) -> None:
    """Take the block out of the ignore file again, so that nothing of it is ever committed."""
    path = root / IGNORE_FILE
    if path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")
        cleaned = without_sandbox_placeholders(text)
        if cleaned != text:
            path.write_text(cleaned, encoding="utf-8")


def _mark_used(env: Mapping[str, str]) -> None:
    """Note that this home is in use, so that ``shelf-cache prune`` keeps it."""
    home = Path(env.get("HOME", ""))
    if not home.is_absolute():
        return
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / ".shelf-used").touch()
    except OSError:  # a home that cannot be written is the installation's problem to report, not this note's
        log.warning("could not mark %s as used", home)


def continuation_prompt(step: RunStep, folder: str, *, ci: str = "") -> str:
    """What an agent is asked when it continues its own session: the round, what changed, the feedback, the output.

    It does not repeat the task: the agent has it, and what it did, in the session it continues.
    """
    role = ROLES[step.phase]
    sent = f"This is round {step.attempt}." if step.attempt else "You have been sent back."
    lines = [
        f"{sent} You are continuing your earlier session on this work.",
        (
            "The working copy is a fresh checkout of the work's branch: it holds what everyone, you included, has "
            "pushed since. Re-read what changed (`git log --stat`, the documents folder) before you answer, and do not "
            "trust the contents of files you remember."
        ),
    ]
    if step.feedback:
        lines += ["", "Address this feedback first:", step.feedback]
    if ci:
        lines += ["", f"What the repository's CI says about this pull request right now:\n{ci}"]
    if role.document:
        lines += ["", f"Write your result to `{folder}/{role.document}`.", "", DOCUMENT_FORMAT_NOTE]
    if step.phase in REVIEWERS:
        lines += [
            "",
            (
                "Before the verdict, say where you stand on your earlier points: a line `REPEATED: <n>` (how many "
                "you raised before that are still unaddressed) and a line `BLOCKING: yes|no` (whether any open "
                "point must be fixed before this can merge)."
            ),
            "End your answer with a single line `VERDICT: APPROVE`, `VERDICT: CHANGES` or `VERDICT: ESCALATE`.",
        ]
    return "\n".join(lines)


def folder_of(root: Path, work_id: WorkId) -> str:
    """The folder a work keeps its documents in: the one it already has (a run that began before ``.shelf``)."""
    old = legacy_documents_dir(work_id)
    return old if (root / old).is_dir() and not (root / documents_dir(work_id)).is_dir() else documents_dir(work_id)


def task_prompt(  # noqa: PLR0913
    work: WorkContext,
    step: RunStep,
    base: str = "main",
    picture: str = "",
    *,
    toolchain: bool = False,
    setup: str = "",
    ci: str = "",
    context: str = "",
    folder: str = "",
    web: bool = False,
    results: Results | None = None,
    depth: ReviewDepth = ReviewDepth.STANDARD,
    sandbox_note: bool = False,
) -> str:
    """What the agent is asked, built from the request, the documents so far and the feedback that sent work back."""
    folder = folder or documents_dir(work.id)
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
    if work.request.autonomy and work.request.autonomy.proceed_on_deadlock:
        lines += ["", UNATTENDED_NOTE]
    if step.feedback:
        lines += ["", f"This is round {step.attempt}. Address this feedback first:", step.feedback]
    if step.phase in REVIEWERS or role.name == "architect":
        lines += ["", f"The base branch is `{base}`: `git diff {base}...HEAD` shows what this work changed."]
    sees_ci = step.phase in CI_PHASES
    notes = [
        f"What the repository's CI says about this pull request right now:\n{ci}" if ci and sees_ci else "",
        context,
        results_note(results or Results(), step.phase),
        review_note(depth, step.phase),
        setup or (TOOLCHAIN_NOTE if toolchain else ""),
        WEB_NOTE if web else "",
        SYSTEM_FILES_NOTE,
        SANDBOX_NOTE if sandbox_note else "",
    ]
    lines += [part for note in notes if note for part in ("", note)]
    if role.document:
        lines += ["", f"Write your result to `{folder}/{role.document}`.", "", DOCUMENT_FORMAT_NOTE]
    if step.phase in REVIEWERS:
        lines += [
            "",
            (
                "Before the verdict, say where you stand on your earlier points: a line `REPEATED: <n>` (how many "
                "you raised before that are still unaddressed) and a line `BLOCKING: yes|no` (whether any open "
                "point must be fixed before this can merge)."
            ),
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
    web: bool = False
    """Whether the agents may read the web: their prompts then say how to treat what they read."""
    nix: bool = False
    """Whether a repository's Nix flake may give the agent its environment (a daemon and a store are then running)."""
    administrators: Callable[[], frozenset[str]] = frozenset[str]
    """The logins of the instance's administrators now, for the record of who decided what."""
    run_records: RunRecords | None = None
    """Where what each agent run did is kept, for diagnosing a work afterwards; none keeps nothing."""
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    """Where other repositories are read from, as reference material put next to the clone (none without it)."""

    async def run(self, work: WorkContext, step: RunStep) -> StepResult:
        """Run ``step`` for ``work``, speak about it on the pull request as the agent it is, and read what came out."""
        if step.phase is Phase.PULL_REQUEST:
            return await self._look_at_the_ci(work, step)
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
            _keep_out_of_the_formatter(workspace.path)
            result, speaker, words = await self._do(work, step, workspace, config, token)
            if recorded and not isinstance(result, Produced):
                await workspace.commit_and_push(f"chore(shelf): record the request for {work.id}")
            if not _is_a_repeated_wait(step, result):
                await self.pulls.comment(work, agent_comment(work.id, speaker, words))
            return result

    async def _look_at_the_ci(self, work: WorkContext, step: RunStep) -> Verified:
        """Once the pull request is ready, what that started must finish before a person is asked to merge."""
        checked, words = _after_ci(await self._wait_for_ci(work), [])
        if not _is_a_repeated_wait(step, checked):
            await self.pulls.comment(work, agent_comment(work.id, "checks", words))
        return checked

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
        sees_ci = step.phase in CI_PHASES
        if step.phase is Phase.CODE_REVIEW:  # what our own label changes and pushes started a moment ago must finish
            ci = await self._wait_for_ci(work)
        else:
            ci = await self._ci_now(work) if sees_ci else Ci(CiState.NONE)
        ci_report = ci.report() if ci.state is not CiState.NONE else ""
        setup = await self._set_up_tools(work, step, workspace)
        prompt = task_prompt(
            work,
            step,
            config.base_branch,
            self._picture(work, workspace),
            toolchain=bool(self.cache_dir) and step.phase in TOOL_PHASES,
            setup=setup.note,
            ci=ci_report,
            context=_context_note(work),
            folder=folder_of(workspace.path, work.id),
            results=config.results,
            web=self.web,
            depth=_depth_for(work, step.phase, config),
            sandbox_note=step.phase in TOOL_PHASES and _uses_prettier(workspace.path),
        )
        sink = RunSink()
        asked = continuation_prompt(step, folder_of(workspace.path, work.id), ci=ci_report) if step.session else prompt
        answer = await self._ask_recorded(
            (work, step, workspace, token), (asked, prompt if step.session else ""), sink, (setup, ci_report)
        )
        role = ROLES[step.phase]
        if step.phase in REVIEWERS:
            reviewed = replace(parse_verdict(answer), usage=sink.usage, session=sink.session_id)
            if (
                step.phase is Phase.CODE_REVIEW
            ):  # a document is not judged by what the repository's CI says of its draft
                if reviewed.verdict is Verdict.APPROVE:  # a run may have started while the reviewer worked
                    ci = await self._wait_for_ci(work)
                reviewed = hold_back_for_ci(reviewed, ci)
            return reviewed, role.name, f"**Verdict: {reviewed.verdict}**\n\n{reviewed.issues}".strip()
        await workspace.commit_and_push(f"chore(shelf): {role.name} for {work.id}")
        return (
            Produced(sink.usage, sink.session_id),
            role.name,
            await self._story(work, step, workspace, config, answer),
        )

    async def record_decision(self, work: WorkContext, record: DecisionRecord) -> None:
        """Append a person's decision to the work's decision log on its branch, committed by the system."""
        repo = work.request.repo
        try:
            config = await self.configs.load(repo)
        except InvalidConfigError:
            config = RepoConfig()
        acting = acted_as(config, record.login, record.phase, admin=record.login in self.administrators())
        token = await self.token_for(repo)
        async with self.workspaces.open(Checkout(repo, token, branch_of(work), config.base_branch)) as workspace:
            target = workspace.path / folder_of(workspace.path, work.id) / DECISIONS_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            existing = target.read_text(encoding="utf-8") if target.exists() else ""
            target.write_text(append_entry(existing, replace(record, acting=acting)), encoding="utf-8")
            await workspace.commit_and_push(f"chore(shelf): record {record.login}'s decision for {work.id}")

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
                f"`git diff {base}...HEAD -- . ':(exclude).shelf' ':(exclude)docs/shelf'`."
            ),
            (
                f"The documents of this work are in `{folder_of(workspace.path, work.id)}/`: they record the request "
                "and the spec, and they are not what the pull request changes."
            ),
        ]
        if work.request.text:
            lines += ["", "The request:", work.request.text.strip()[:2000]]
        picture = self._picture(work, workspace)
        return "\n".join([*lines, "", picture] if picture else lines)

    async def _ask_recorded(
        self,
        where: tuple[WorkContext, RunStep, Workspace, str],
        prompts: tuple[str, str],
        sink: RunSink,
        told: tuple[ToolSetup, str],
    ) -> str:
        """Ask the agent and keep what the run did, whether it finished or failed; keeping it never stops the step."""
        work, step, workspace, token = where
        setup, ci_report = told
        started = self.now()
        try:
            answer = await self._ask_agent(work, step, workspace, token, prompts, sink, setup.env)
        except Exception as error:
            await self._keep_run(
                work, step, sink, started, (setup, ci_report), outcome="failed", answer="", error=error
            )
            raise
        await self._keep_run(work, step, sink, started, (setup, ci_report), outcome="finished", answer=answer)
        return answer

    async def _keep_run(  # noqa: PLR0913 - what one record is made of
        self,
        work: WorkContext,
        step: RunStep,
        sink: RunSink,
        started: datetime,
        told: tuple[ToolSetup, str],
        *,
        outcome: str,
        answer: str,
        error: Exception | None = None,
    ) -> None:
        if self.run_records is None:
            return
        setup, ci_report = told
        try:
            used = sink.usage or Usage()
            await self.run_records.write(
                RunRecord(
                    work_id=str(work.id),
                    phase=step.phase.name.lower(),
                    attempt=step.attempt,
                    role=ROLES[step.phase].name,
                    started=started.isoformat(timespec="seconds"),
                    ended=self.now().isoformat(timespec="seconds"),
                    outcome=outcome,
                    model=self.model or (used.models[0] if used.models else ""),
                    usage=used,
                    session=sink.session_id,
                    resumed=bool(step.session) and not sink.fell_back,
                    fell_back=sink.fell_back,
                    subtype=sink.subtype,
                    stop_reason=sink.stop_reason,
                    terminal_reason=sink.terminal_reason,
                    api_error_status=sink.api_error_status,
                    error=sink.error or (redact(" ".join(str(error).split()))[:400] if error else ""),
                    errors=tuple(sink.errors),
                    denials=tuple(sink.denials),
                    setup=setup.note,
                    ci=ci_report,
                    tools=keep_events(sink.tools),
                    tool_calls=len(sink.tools),
                    web=self.web,
                    max_turns=self.max_turns,
                    answer_chars=len(answer),
                    repo=work.request.repo.full_name,
                    requester=work.request.requester,
                    entry=work.request.entry.value,
                )
            )
        except Exception:
            log.warning("could not keep the record of a run of %s", work.id, exc_info=True)

    async def _ask_agent(  # noqa: PLR0913, PLR0917 - one argument per thing the agent needs
        self,
        work: WorkContext,
        step: RunStep,
        workspace: Workspace,
        token: str,
        prompts: tuple[str, str],
        sink: RunSink,
        more_env: Mapping[str, str],
    ) -> str:
        """Ask the agent: ``prompts`` is what to ask and, for a session continued, the whole task to fall back on."""
        prompt, fallback = prompts
        role = ROLES[step.phase]
        hidden = step.phase in TOOL_PHASES and _hide_sandbox_placeholders(workspace.path)
        try:
            return await self._run_agent(role, prompt, fallback, (work, step, workspace, token), sink, more_env)
        finally:
            if hidden:
                _show_sandbox_placeholders_again(workspace.path)

    async def _run_agent(  # noqa: PLR0913, PLR0917 - one argument per thing the agent needs
        self,
        role: AgentRole,
        prompt: str,
        fallback: str,
        where: tuple[WorkContext, RunStep, Workspace, str],
        sink: RunSink,
        more_env: Mapping[str, str],
    ) -> str:
        work, step, workspace, token = where
        return await self.agents.run(
            AgentTask(
                role=role,
                system_prompt=self.prompt_for(role.name),
                prompt=prompt,
                resume=step.session,
                fallback_prompt=fallback,
                workdir=workspace.path,
                env={
                    **(self._toolchain_env(work, workspace)),
                    **more_env,
                    **({"GH_TOKEN": token} if step.phase is Phase.IMPLEMENT else {}),
                },
                max_turns=self.max_turns,
                max_budget_usd=self.max_budget_usd,
                model=self.model,
                sink=sink,
            )
        )

    async def _set_up_tools(self, work: WorkContext, step: RunStep, workspace: Workspace) -> ToolSetup:
        """Make the repository's tools available before the agent starts, when it declares none of its own.

        It runs here in the worker, outside the agent's sandbox, which can write nothing but its working directory, and
        installs into the repository's own home, so the next piece of work on this repository finds it there. Only plain
        versions of node, python, go and java are ever installed, and a Nix flake is used only when Nix is on and the
        repository's CI runs through Nix or sets up nothing else. The answer is what the agent is told and what is
        added to its environment: nothing when there is nothing to say.
        """
        if not self.cache_dir or step.phase not in TOOL_PHASES:
            return ToolSetup()
        files = _read_sources(workspace.path)
        env = self._toolchain_env(work, workspace)
        if is_declared(files):
            _mark_used(env)
            return await self._install_declared(work, workspace, env, files)
        tools = detect_tools(files)
        if self.nix and has_flake(files) and (ci_uses_nix(files) or not tools):
            _mark_used(env)
            return await self._flake_environment(work, workspace, env)
        if not tools:
            return ToolSetup()
        _mark_used(env)
        return await self._install_tools(work, workspace, env, tools)

    async def _install_declared(
        self, work: WorkContext, workspace: Workspace, env: Mapping[str, str], files: Mapping[str, str]
    ) -> ToolSetup:
        """Install the plain tools the repository's mise declaration names, here and not in the sandbox.

        The declaration itself is never run: its tools and versions are read and installed with ``mise use --global``,
        so that its hooks, plugins, environment scripts and tool options do nothing in the worker.
        """
        declared = declared_tools(files)
        ignored = (*declared.ignored, *(f"{name} section" for name in ignored_sections(files)))
        if not declared.tools:
            return ToolSetup(nothing_to_install(ignored))
        try:
            done = await asyncio.wait_for(workspace.run(setup_command(env, declared.tools)), SETUP_TIMEOUT)
        except TimeoutError:
            return ToolSetup(declared_failed(f"it took longer than {int(SETUP_TIMEOUT // 60)} minutes"))
        except Exception as error:  # noqa: BLE001 - told to the agent, never fatal
            log.warning("could not install the declared tools of %s: %s", work.request.repo.full_name, error)
            return ToolSetup(declared_failed("it could not be run"))
        if done.exit_code != 0:
            last = next((line for line in reversed(done.output.strip().splitlines()) if line.strip()), "no output")
            return ToolSetup(declared_failed(last[:200]))
        return ToolSetup(declared_ready(declared.tools, tuple(ignored)))

    async def _install_tools(
        self, work: WorkContext, workspace: Workspace, env: Mapping[str, str], tools: Mapping[str, str]
    ) -> ToolSetup:
        """Install ``tools`` into the repository's home with mise, and say how it went."""
        try:
            done = await asyncio.wait_for(workspace.run(setup_command(env, tools)), SETUP_TIMEOUT)
        except TimeoutError:
            return ToolSetup(tools_failed(tools, f"it took longer than {int(SETUP_TIMEOUT // 60)} minutes"))
        except Exception as error:  # noqa: BLE001 - tools that did not install are told to the agent, never fatal
            log.warning("could not set up the tools of %s: %s", work.request.repo.full_name, error)
            return ToolSetup(tools_failed(tools, "it could not be run"))
        if done.exit_code != 0:
            last = next((line for line in reversed(done.output.strip().splitlines()) if line.strip()), "no output")
            return ToolSetup(tools_failed(tools, last[:200]))
        note = tools_ready(tools)
        if (
            "node" in tools
            and not workspace.path.joinpath("node_modules").exists()
            and workspace.path.joinpath("package-lock.json").is_file()
        ):
            note = f"{note}\n\n{await self._install_dependencies(workspace, env)}"
        return ToolSetup(note)

    async def _install_dependencies(self, workspace: Workspace, env: Mapping[str, str]) -> str:
        """Install the locked Node dependencies in the clone, here and not in the sandbox, and say how it went."""
        try:
            done = await asyncio.wait_for(workspace.run(dependencies_command(env)), SETUP_TIMEOUT)
        except TimeoutError:
            return dependencies_failed(f"it took longer than {int(SETUP_TIMEOUT // 60)} minutes")
        except Exception as error:  # noqa: BLE001 - told to the agent, never fatal
            log.warning("could not install the dependencies: %s", error)
            return dependencies_failed("it could not be run")
        if done.exit_code != 0:
            last = next((line for line in reversed(done.output.strip().splitlines()) if line.strip()), "no output")
            return dependencies_failed(last[:200])
        return dependencies_ready()

    async def _flake_environment(self, work: WorkContext, workspace: Workspace, env: Mapping[str, str]) -> ToolSetup:
        """The environment of the repository's flake development shell, asked of Nix without entering the shell."""
        try:
            done = await asyncio.wait_for(workspace.run(print_dev_env_command(env["HOME"])), TIME_LIMIT + 30)
        except TimeoutError:
            return ToolSetup(nix_failed(f"it took longer than {TIME_LIMIT // 60} minutes"))
        except Exception as error:  # noqa: BLE001 - told to the agent, never fatal
            log.warning("could not use the flake of %s: %s", work.request.repo.full_name, error)
            return ToolSetup(nix_failed("it could not be run"))
        if done.exit_code != 0:
            last = next((line for line in reversed(done.output.strip().splitlines()) if line.strip()), "no output")
            return ToolSetup(nix_failed(last[:200]))
        path, variables = dev_environment(done.output)
        if not path:
            return ToolSetup(nix_failed("it printed no usable environment"))
        return ToolSetup(nix_ready(len(variables)), {**variables, "PATH": f"{path}:{env['PATH']}"})

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
            str(p.relative_to(root))
            for pattern in EARLIER_WORK
            for p in root.glob(pattern)
            if p.is_file() and work.id not in p.parts
        )
        return context_brief(found, earlier)

    async def _record_request(self, work: WorkContext, workspace: Workspace) -> bool:
        """Write the text the person submitted into the repository, once, so everyone reads the same document."""
        name = PROVIDED_DOCUMENT.get(work.request.entry)
        if name is None or not work.request.text.strip():
            return False
        target = workspace.path / folder_of(workspace.path, work.id) / name
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
            path = f"{folder_of(workspace.path, work.id)}/{role.document}"
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
            if config.checks:
                lines += await self._tools_for_the_checks(work, workspace)
            local, more = await self._local_checks(workspace, config, self._toolchain_env(work, workspace))
            lines += more
            if not local.passed:  # no point waiting for a CI that will only repeat it
                return local, "**Failed**\n\n" + "\n".join(lines) + f"\n\n```\n{local.report}\n```"
        ci = await self._wait_for_ci(work)
        return _after_ci(ci, lines)

    async def _tools_for_the_checks(self, work: WorkContext, workspace: Workspace) -> list[str]:
        """Install what the clone declares or its CI uses before its checks run; a line only when that failed."""
        if not self.cache_dir:
            return []
        setup = await self._set_up_tools(work, RunStep(Phase.IMPLEMENT, 0, ""), workspace)
        failed = "failed" in setup.note[:200] or "could not" in setup.note[:200]
        return [f"⚠️ {setup.note.split('. ')[0]}"] if failed else []

    async def _local_checks(
        self, workspace: Workspace, config: RepoConfig, env: Mapping[str, str]
    ) -> tuple[Verified, list[str]]:
        """Run the repository's own commands; the lines say what each did."""
        if not config.checks:
            return Verified(passed=True), [NOTHING_VERIFIED]
        failures: list[str] = []
        lines: list[str] = []
        for command in config.checks:
            result = await workspace.run(with_environment(env, command))
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
                return ci.given_up() if ci.only_cancelled else ci
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
            return replace(
                reviewed,
                verdict=Verdict.CHANGES,
                blocking=True,
                issues=f"{reviewed.issues}\n\nNot approved: the CI is red.\n{ci.report()}".strip(),
            )
        case CiState.PENDING | CiState.BLOCKED:
            return replace(
                reviewed,
                verdict=Verdict.ESCALATE,
                blocking=True,
                issues=f"{reviewed.issues}\n\nNot approved yet: the CI has not finished.\n{ci.report()}".strip(),
            )
        case CiState.GREEN | CiState.NONE:
            return reviewed


def _context_note(work: WorkContext) -> str:
    """What the agent is told about the reference repositories of this work, nothing when it has none."""
    found = [parse_context(spec) for spec in work.request.context]
    return note_for(tuple(item.value for item in found if isinstance(item, Ok))) if work.request.context else ""
