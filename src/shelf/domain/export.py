"""One work as a single Markdown file, for debugging it somewhere else. Pure: the facts in, the text out."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from shelf.domain.guard import StoppedCall
from shelf.domain.roles import DOCUMENT_TITLES
from shelf.domain.runlog import RunRecord
from shelf.domain.story import Message
from shelf.domain.usage import UsageSummary

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{1,80}")


def filename(work_id: str) -> str:
    """``shelf-<work id>.md``, with nothing in the name that a header or a disk could trip on."""
    safe = work_id if _SAFE_ID.fullmatch(work_id) else re.sub(r"[^A-Za-z0-9._-]", "_", work_id)[:80] or "work"
    return f"shelf-{safe}.md"


def fenced(text: str, language: str = "markdown") -> str:
    """``text`` in a fenced block nothing inside it can close: the fence is longer than any run of backticks in it."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text.rstrip()}\n{fence}"


@dataclass(frozen=True, slots=True)
class ExportStep:
    """One step of the pipeline as the page shows it."""

    label: str
    state: str
    at: str = ""


@dataclass(frozen=True, slots=True)
class WorkExport:
    """Everything the file says about a work; a part that could not be read is ``None`` and the file says so."""

    work_id: str
    facts: Sequence[tuple[str, str]]
    steps: Sequence[ExportStep]
    request: str
    conversation: Sequence[Message] | None
    documents: Mapping[str, str] | None
    usage: UsageSummary | None
    generated: str
    guard: Sequence[StoppedCall] | None = None
    """The calls the guard flagged, newest first; ``None`` when it could not be read."""
    started: str = ""
    """When the work's first step happened (ISO), the start of the window the guard's calls are kept from."""
    ended: str = ""
    """When the work last did anything (ISO); empty while it runs, so the window ends now."""
    runs: Sequence[RunRecord] | None = None
    """The record of each agent run, oldest first; ``None`` when no store of records is kept."""


def _facts(facts: Sequence[tuple[str, str]]) -> list[str]:
    return ["## The work", "", *(f"- **{name}:** {value}" for name, value in facts if value), ""]


def _steps(steps: Sequence[ExportStep]) -> list[str]:
    if not steps:
        return ["## Steps", "", "_Not known: the workflow engine no longer holds this work._", ""]
    lines = ["## Steps", "", "| Step | State | When |", "| --- | --- | --- |"]
    lines += [f"| {step.label} | {step.state} | {step.at or '-'} |" for step in steps]
    return [*lines, ""]


def _conversation(story: Sequence[Message] | None) -> list[str]:
    lines = ["## Conversation", ""]
    if story is None:
        return [*lines, "_The conversation could not be read from GitHub when this file was made._", ""]
    shown = [message for message in story if message.body.strip()]
    if not shown:
        return [*lines, "_No comment yet._", ""]
    for number, message in enumerate(shown, start=1):
        when = f" · {message.when}" if message.when else ""
        lines += [f"### {number}. {message.speaker} ({message.voice.value}){when}", "", fenced(message.body), ""]
    return lines


def _documents(documents: Mapping[str, str] | None) -> list[str]:
    lines = ["## Documents", ""]
    if documents is None:
        return [*lines, "_The documents could not be read from GitHub when this file was made._", ""]
    names = [name for name in DOCUMENT_TITLES if name in documents]
    names += sorted(name for name in documents if name not in DOCUMENT_TITLES)
    if not names:
        return [*lines, "_No document yet._", ""]
    for name in names:
        lines += [f"### {DOCUMENT_TITLES.get(name, name)} (`{name}`)", "", fenced(documents[name]), ""]
    return lines


def _usage(usage: UsageSummary | None) -> list[str]:
    lines = ["## What the agents used", ""]
    if usage is None or not usage.steps:
        return [*lines, "_Nothing was recorded for this work._", ""]
    total = usage.total
    cost = f"${total.cost_usd:.2f}" if total.cost_usd is not None else "cost not reported"
    lines += [
        (
            f"Total: {total.tokens:,} tokens ({total.input_tokens:,} read, {total.output_tokens:,} written, "
            f"{total.cache_read_tokens:,} from cache, {total.cache_write_tokens:,} into cache), {cost}, "
            f"{total.turns} turns, {round(total.seconds)} s."
        ),
        "",
        "| Agent | Ran | Turns | Seconds | Tokens | Cost |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for agent in usage.agents:
        cost = f"${agent.usage.cost_usd:.2f}" if agent.usage.cost_usd is not None else "n/a"
        lines.append(
            f"| {agent.agent} | {agent.runs} | {agent.usage.turns} | {round(agent.usage.seconds)} | "
            f"{agent.usage.tokens:,} | {cost} |"
        )
    lines += [
        "",
        "| Step | Round | Agent | Turns | Seconds | Read | Written | Cache | Cost |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for step in usage.steps:
        cost = f"${step.usage.cost_usd:.2f}" if step.usage.cost_usd is not None else "n/a"
        cache = step.usage.cache_read_tokens + step.usage.cache_write_tokens
        lines.append(
            f"| {step.phase} | {step.attempt} | {step.agent} | {step.usage.turns} | {round(step.usage.seconds)} | "
            f"{step.usage.input_tokens:,} | {step.usage.output_tokens:,} | {cache:,} | {cost} |"
        )
    return [*lines, ""]


def _moment(iso: str) -> datetime | None:
    """An ISO time as an aware UTC moment; a time with no zone is UTC, and nothing readable gives ``None``."""
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def in_window(calls: Sequence[StoppedCall], started: str, ended: str) -> list[StoppedCall]:
    """The calls made between ``started`` and ``ended`` (open ends when unknown), oldest first."""
    begin, end = _moment(started), _moment(ended)
    kept: list[tuple[datetime, StoppedCall]] = []
    for call in calls:
        when = _moment(call.at)
        if when is None or (begin and when < begin) or (end and when > end):
            continue
        kept.append((when, call))
    return [call for _, call in sorted(kept, key=lambda pair: pair[0])]


def _guard(export: WorkExport) -> list[str]:
    lines = ["## What the guard flagged while the work ran", ""]
    if export.guard is None:
        return [*lines, "_The guard could not be read when this file was made._", ""]
    found = in_window(export.guard, export.started, export.ended)
    begin = _moment(export.started)
    oldest = min((m for call in export.guard if (m := _moment(call.at)) is not None), default=None)
    if begin and oldest and oldest > begin and export.guard:
        lines += ["_The guard keeps only its latest flagged calls: earlier ones may be missing from this list._", ""]
    if not found:
        return [*lines, "_The guard flagged nothing in that time._", ""]
    lines += ["| When (UTC) | Agent | What | Risks | Why | Result |", "| --- | --- | --- | --- | --- | --- |"]
    for call in found:
        stopped = call.decision in ("deny", "ask")
        result = "stopped" if stopped else f"not stopped (recorded; the policy meant {call.intended or call.decision})"
        what = call.summary.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {call.at[:19].replace('T', ' ')} | {call.agent} | `{what}` | {', '.join(call.categories)} | "
            f"{call.reason.replace('|', '/')} | {result} |"
        )
    return [*lines, ""]


def _run(number: int, run: RunRecord) -> list[str]:
    failed = [event for event in run.tools if not event.ok]
    head = f"### {number}. {run.role} · {run.phase}, round {run.attempt} · {run.outcome}"
    lines = [head, ""]
    facts = [
        ("Began / ended", f"{run.started or '-'} / {run.ended or '-'}"),
        ("Model", run.model),
        (
            "Session",
            "continued"
            if run.resumed
            else "started again after one could not be continued"
            if run.fell_back
            else "new",
        ),
        ("Stopped because", ", ".join(x for x in (run.subtype, run.stop_reason, run.terminal_reason) if x)),
        ("API error status", str(run.api_error_status) if run.api_error_status else ""),
        ("Error", run.error),
        ("Errors reported", " | ".join(run.errors)),
        (
            "Used",
            f"{run.usage.tokens:,} tokens, {run.usage.turns} of {run.max_turns} turns, {round(run.usage.seconds)} s",
        ),
        ("Told about tools", " ".join(run.setup.split())[:500]),
        ("CI when it started", " ".join(run.ci.split())[:500]),
        ("Web", "on" if run.web else "off"),
        ("Tool calls", f"{run.tool_calls}, of which {len(failed)} failed"),
    ]
    lines += [f"- **{name}:** {value}" for name, value in facts if value]
    if run.denials:
        lines += ["", "Refused by the agent's permissions:", *[f"- `{d}`" for d in run.denials]]
    if run.tools:
        lines += ["", "| # | Tool | What | Result |", "| --- | --- | --- | --- |"]
        for index, event in enumerate(run.tools, start=1):
            what = event.summary.replace("|", "\\|")
            result = "ok" if event.ok else f"FAILED: {event.note.replace('|', '/')}"
            lines.append(f"| {index} | {event.name} | `{what}` | {result} |")
    return [*lines, ""]


def _runs(export: WorkExport) -> list[str]:
    lines = ["## Agent runs", ""]
    if export.runs is None:
        return [*lines, "_This instance keeps no record of agent runs._", ""]
    if not export.runs:
        return [
            *lines,
            "_No run record was kept for this work: it ran before they were kept, or this instance did not keep them._",
            "",
        ]
    for number, run in enumerate(export.runs, start=1):
        lines += _run(number, run)
    return lines


def render(export: WorkExport) -> str:
    """The whole file."""
    lines = [
        f"# Work {export.work_id}",
        "",
        f"_Exported {export.generated}. Made by the Download button of the work's page, to debug it elsewhere._",
        "",
        *_facts(export.facts),
        *_steps(export.steps),
        "## The request",
        "",
        fenced(export.request) if export.request.strip() else "_No request text was kept._",
        "",
        *_conversation(export.conversation),
        *_documents(export.documents),
        *_usage(export.usage),
        *_guard(export),
        *_runs(export),
    ]
    return "\n".join(lines).rstrip() + "\n"
