"""What happened in one agent run, kept so that a work can be diagnosed afterwards. Pure: no clock, no I/O."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from shelf.domain.usage import Usage

SUMMARY_LIMIT = 160
NOTE_LIMIT = 240
MAX_EVENTS = 300
"""The most tool calls one run keeps: the failures are kept first, the rest in order until this many."""

_SECRETS = (
    re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\b(authorization:\s*bearer|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b([A-Za-z0-9_]*(?:token|secret|password|passwd|api[_-]?key)[A-Za-z0-9_]*)=[^\s'\"]{6,}"),
)


def redact(text: str) -> str:
    """``text`` with what looks like a credential replaced: a record is read by people who never saw the run."""
    for pattern in _SECRETS[:-1]:
        text = pattern.sub("[redacted]", text)
    return _SECRETS[-1].sub(lambda match: f"{match.group(1)}=[redacted]", text)


@dataclass(frozen=True, slots=True)
class ToolEvent:
    """One tool call of an agent: which, on what (shortened, redacted), whether it worked and why not."""

    name: str
    summary: str
    ok: bool = True
    note: str = ""
    """For a failure: the start of what the tool said."""


def tool_summary(_name: str, arguments: Mapping[str, Any]) -> str:
    """What a call was about, in one short redacted line: the command, the path, the address or the pattern."""
    for key in ("command", "file_path", "path", "url", "query", "pattern", "notebook_path"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return redact(" ".join(value.split()))[:SUMMARY_LIMIT]
    return ""


def _text_of(block: object) -> str:
    if not isinstance(block, dict):
        return ""
    text = cast("dict[str, Any]", block).get("text")
    return text if isinstance(text, str) else ""


def result_note(content: object) -> str:
    """The start of what a failed tool said, from a result that is a text or a list of blocks."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = " ".join(_text_of(block) for block in cast("list[object]", content))
    else:
        text = ""
    return redact(" ".join(text.split()))[:NOTE_LIMIT]


@dataclass(frozen=True, slots=True)
class RunRecord:
    """What one agent run did, as far as the system saw it."""

    work_id: str
    phase: str
    attempt: int
    role: str
    started: str
    ended: str
    outcome: str
    """``finished``, or ``failed`` when the run raised."""
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    session: str = ""
    resumed: bool = False
    """Whether the run continued an earlier session."""
    fell_back: bool = False
    """Whether a session that could not be continued was started again from the whole task."""
    subtype: str = ""
    stop_reason: str = ""
    terminal_reason: str = ""
    api_error_status: int | None = None
    error: str = ""
    errors: tuple[str, ...] = ()
    denials: tuple[str, ...] = ()
    """The tool calls the agent's permissions refused, shortened."""
    setup: str = ""
    """What the worker told the agent about its tools (installed, failed, none)."""
    ci: str = ""
    """What the CI said when the step started, for the steps that are told."""
    tools: tuple[ToolEvent, ...] = ()
    tool_calls: int = 0
    """How many calls the agent made, including the ones not kept in ``tools``."""
    web: bool = False
    max_turns: int = 0
    answer_chars: int = 0


def keep_events(events: Sequence[ToolEvent]) -> tuple[ToolEvent, ...]:
    """At most ``MAX_EVENTS`` calls, in order: every failure, then as many of the others as fit."""
    if len(events) <= MAX_EVENTS:
        return tuple(events)
    failed = {index for index, event in enumerate(events) if not event.ok}
    room = max(0, MAX_EVENTS - len(failed))
    others = [index for index in range(len(events)) if index not in failed][:room]
    return tuple(events[index] for index in sorted(failed | set(others)))


def to_data(record: RunRecord) -> dict[str, Any]:
    """The record as plain data, for a file."""
    usage = record.usage
    return {
        "work_id": record.work_id,
        "phase": record.phase,
        "attempt": record.attempt,
        "role": record.role,
        "started": record.started,
        "ended": record.ended,
        "outcome": record.outcome,
        "model": record.model,
        "usage": {
            "input": usage.input_tokens,
            "output": usage.output_tokens,
            "cache_read": usage.cache_read_tokens,
            "cache_write": usage.cache_write_tokens,
            "cost": usage.cost_usd,
            "turns": usage.turns,
            "seconds": usage.seconds,
            "models": list(usage.models),
        },
        "session": record.session,
        "resumed": record.resumed,
        "fell_back": record.fell_back,
        "subtype": record.subtype,
        "stop_reason": record.stop_reason,
        "terminal_reason": record.terminal_reason,
        "api_error_status": record.api_error_status,
        "error": record.error,
        "errors": list(record.errors),
        "denials": list(record.denials),
        "setup": record.setup,
        "ci": record.ci,
        "tools": [[e.name, e.summary, e.ok, e.note] for e in record.tools],
        "tool_calls": record.tool_calls,
        "web": record.web,
        "max_turns": record.max_turns,
        "answer_chars": record.answer_chars,
    }


def from_data(data: Mapping[str, Any]) -> RunRecord:
    """A record from what ``to_data`` wrote; a value that is missing is its default, so an older file still reads."""
    used: Mapping[str, Any] = data.get("usage") or {}
    return RunRecord(
        work_id=str(data.get("work_id", "")),
        phase=str(data.get("phase", "")),
        attempt=int(data.get("attempt", 0)),
        role=str(data.get("role", "")),
        started=str(data.get("started", "")),
        ended=str(data.get("ended", "")),
        outcome=str(data.get("outcome", "")),
        model=str(data.get("model", "")),
        usage=Usage(
            int(used.get("input", 0)),
            int(used.get("output", 0)),
            int(used.get("cache_read", 0)),
            int(used.get("cache_write", 0)),
            used.get("cost"),
            int(used.get("turns", 0)),
            float(used.get("seconds", 0.0)),
            tuple(str(m) for m in used.get("models", [])),
        ),
        session=str(data.get("session", "")),
        resumed=bool(data.get("resumed", False)),
        fell_back=bool(data.get("fell_back", False)),
        subtype=str(data.get("subtype", "")),
        stop_reason=str(data.get("stop_reason", "")),
        terminal_reason=str(data.get("terminal_reason", "")),
        api_error_status=data.get("api_error_status"),
        error=str(data.get("error", "")),
        errors=tuple(str(e) for e in data.get("errors", [])),
        denials=tuple(str(d) for d in data.get("denials", [])),
        setup=str(data.get("setup", "")),
        ci=str(data.get("ci", "")),
        tools=tuple(ToolEvent(str(e[0]), str(e[1]), bool(e[2]), str(e[3])) for e in data.get("tools", [])),
        tool_calls=int(data.get("tool_calls", 0)),
        web=bool(data.get("web", False)),
        max_turns=int(data.get("max_turns", 0)),
        answer_chars=int(data.get("answer_chars", 0)),
    )
