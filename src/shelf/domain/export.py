"""One work as a single Markdown file, for debugging it somewhere else. Pure: the facts in, the text out."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from shelf.domain.roles import DOCUMENT_TITLES
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


def _facts(facts: Sequence[tuple[str, str]]) -> list[str]:
    return ["## The work", "", *(f"- **{name}:** {value}" for name, value in facts if value), ""]


def _steps(steps: Sequence[ExportStep]) -> list[str]:
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
    ]
    return "\n".join(lines).rstrip() + "\n"
