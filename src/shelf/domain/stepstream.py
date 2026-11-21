"""What an agent step in a container says about itself: JSON lines, versioned, read tolerantly. Pure: no I/O.

The code in the container writes ``hello``, then ``tool``, ``tool_result``, ``audit``, ``result`` and ``ping`` lines.
Whoever runs the container writes the last line, ``exit``: the agent never does, so a step that dies cannot claim it
succeeded.
A reader ignores any field and any kind of line it does not know, so a newer sender never breaks an older worker; a
stream that stops without ``exit`` is a failure whatever came before it.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Final, NoReturn, cast

from shelf.domain.runlog import NOTE_LIMIT, SUMMARY_LIMIT, ToolEvent, redact
from shelf.domain.usage import Usage

PROTOCOL: Final = 1
"""The version of the stream this code writes and reads. A newer sender is refused: only added fields are tolerated."""

KEPT_ERRORS: Final = 300
"""How much of one error the worker keeps, as the record of a run always did."""

REASONS: Final = {
    "timeout": "the step ran out of time",
    "killed": "the step was stopped",
    "oom": "the step ran out of memory",
    "engine": "the runner could not run the step",
}
"""Why a container ended when it was not the agent's own end. Anything else is shown as a plain exit code."""


class StreamError(RuntimeError):
    """The stream broke the protocol. The message names the problem, never the offending line: it may hold a secret."""


def _fail(message: str) -> NoReturn:
    raise StreamError(message)


@dataclass(frozen=True, slots=True)
class Hello:
    """The first line: which version of the protocol the sender speaks."""

    version: int = PROTOCOL


@dataclass(frozen=True, slots=True)
class Tool:
    """The agent called a tool."""

    id: str
    name: str
    summary: str = ""


@dataclass(frozen=True, slots=True)
class ToolResult:
    """A tool call ended; only a failure is of interest."""

    id: str
    error: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class Audit:
    """Warden wrote a record to the spool; ``n`` is how many it holds so far."""

    n: int = 0


@dataclass(frozen=True, slots=True)
class Result:
    """How the run ended, from the agent's side."""

    is_error: bool = False
    result: str = ""
    session: str = ""
    usage: Usage = field(default_factory=Usage)
    subtype: str = ""
    stop_reason: str = ""
    terminal_reason: str = ""
    api_error_status: int | None = None
    errors: tuple[str, ...] = ()
    denials: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Check:
    """How a repository's check command ended: its exit code and the end of its output."""

    code: int = 0
    output: str = ""


@dataclass(frozen=True, slots=True)
class Ping:
    """A keepalive, so that nothing between the container and the worker takes a quiet step for a dead one."""


@dataclass(frozen=True, slots=True)
class Exit:
    """How the container ended, said by whoever ran it: ``reason`` is ``timeout``, ``killed``, ``oom`` or empty."""

    code: int = 0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Unknown:
    """A line of a kind this code does not know: ignored, so a newer sender does not break an older reader."""

    kind: str


Event = Hello | Tool | ToolResult | Audit | Result | Check | Ping | Exit | Unknown


def _usage_to_data(usage: Usage) -> dict[str, Any]:
    return {
        "input": usage.input_tokens,
        "output": usage.output_tokens,
        "cache_read": usage.cache_read_tokens,
        "cache_write": usage.cache_write_tokens,
        "cost": usage.cost_usd,
        "turns": usage.turns,
        "seconds": usage.seconds,
        "models": list(usage.models),
    }


def encode(event: Event) -> str:
    """The line for ``event``, without the newline."""
    match event:
        case Hello(version):
            data: dict[str, Any] = {"e": "hello", "v": version}
        case Tool(id, name, summary):
            data = {"e": "tool", "id": id, "name": name, "summary": summary}
        case ToolResult(id, error, note):
            data = {"e": "tool_result", "id": id, "error": error, "note": note}
        case Audit(n):
            data = {"e": "audit", "n": n}
        case Result() as done:
            data = {
                "e": "result",
                "is_error": done.is_error,
                "result": done.result,
                "session": done.session,
                "usage": _usage_to_data(done.usage),
                "subtype": done.subtype,
                "stop_reason": done.stop_reason,
                "terminal_reason": done.terminal_reason,
                "api_error_status": done.api_error_status,
                "errors": list(done.errors),
                "denials": list(done.denials),
            }
        case Check(code, output):
            data = {"e": "check", "code": code, "output": output}
        case Ping():
            data = {"e": "ping"}
        case Exit(code, reason):
            data = {"e": "exit", "code": code, **({"reason": reason} if reason else {})}
        case Unknown(kind):
            data = {"e": kind}
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        _fail(f"the field {key} is not text")
    return value


def _whole(data: Mapping[str, Any], key: str, *, default: int = 0) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(f"the field {key} is not a whole number")
    return value


def _flag(data: Mapping[str, Any], key: str) -> bool:
    value = data.get(key, False)
    if not isinstance(value, bool):
        _fail(f"the field {key} is not true or false")
    return value


def _texts(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value: object = data.get(key) or []
    if not isinstance(value, list):
        _fail(f"the field {key} is not a list")
    return tuple(str(item) for item in cast("list[object]", value))


def _number(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        _fail(f"the field {key} is not a number")
    return float(value)


def _usage_from_data(value: object) -> Usage:
    if value is None:
        return Usage()
    if not isinstance(value, dict):
        _fail("the field usage is not an object")
    data = cast("dict[str, Any]", value)
    cost = _number(data, "cost")
    return Usage(
        input_tokens=_whole(data, "input"),
        output_tokens=_whole(data, "output"),
        cache_read_tokens=_whole(data, "cache_read"),
        cache_write_tokens=_whole(data, "cache_write"),
        cost_usd=cost,
        turns=_whole(data, "turns"),
        seconds=_number(data, "seconds") or 0.0,
        models=_texts(data, "models"),
    )


def _read_result(data: Mapping[str, Any]) -> Result:
    status = data.get("api_error_status")
    if status is not None and (isinstance(status, bool) or not isinstance(status, int)):
        _fail("the field api_error_status is not a whole number")
    return Result(
        is_error=_flag(data, "is_error"),
        result=_text(data, "result"),
        session=_text(data, "session"),
        usage=_usage_from_data(data.get("usage")),
        subtype=_text(data, "subtype"),
        stop_reason=_text(data, "stop_reason"),
        terminal_reason=_text(data, "terminal_reason"),
        api_error_status=status,
        errors=tuple(redact(error)[:KEPT_ERRORS] for error in _texts(data, "errors")),
        denials=tuple(redact(denied)[:SUMMARY_LIMIT] for denied in _texts(data, "denials")),
    )


_READERS: Final[dict[str, Callable[[Mapping[str, Any]], Event]]] = {
    "hello": lambda data: Hello(_whole(data, "v", default=1)),
    "tool": lambda data: Tool(_text(data, "id"), _text(data, "name"), redact(_text(data, "summary"))[:SUMMARY_LIMIT]),
    "tool_result": lambda data: ToolResult(
        _text(data, "id"), _flag(data, "error"), redact(_text(data, "note"))[:NOTE_LIMIT]
    ),
    "audit": lambda data: Audit(_whole(data, "n")),
    "result": _read_result,
    "check": lambda data: Check(_whole(data, "code"), redact(_text(data, "output"))),
    "ping": lambda _data: Ping(),
    "exit": lambda data: Exit(_whole(data, "code"), _text(data, "reason")),
}


def decode(line: str) -> Event:
    """The event a line holds. Raises ``StreamError`` for what is not JSON or breaks the shape of a known kind."""
    try:
        parsed: object = json.loads(line)
    except ValueError:
        message = "a line of the step is not JSON"
        raise StreamError(message) from None
    if not isinstance(parsed, dict):
        _fail("a line of the step is not an object")
    data = cast("dict[str, Any]", parsed)
    kind = data.get("e")
    if not isinstance(kind, str) or not kind:
        _fail("a line of the step has no kind")
    read = _READERS.get(kind)
    return read(data) if read is not None else Unknown(kind)


@dataclass(eq=False)
class StepStream:
    """What the lines of one step add up to. Feed it line by line; ask for the failure when the stream ends."""

    tools: list[ToolEvent] = field(default_factory=list[ToolEvent])
    result: Result | None = None
    check: Check | None = None
    exit: Exit | None = None
    audits: int = 0
    _started: bool = False
    _calls: dict[str, int] = field(default_factory=dict[str, int])

    def feed(self, line: str) -> None:
        """Take one line. Blank lines are skipped; anything after ``exit`` is a protocol error."""
        if not line.strip():
            return
        event = decode(line)
        if self.exit is not None:
            _fail("the step spoke after it had exited")
        if isinstance(event, Ping | Unknown):
            return
        if not self._started:
            if isinstance(event, Exit):  # the container ended before the step said anything: ``failure`` says so
                self.exit = event
                return
            if not isinstance(event, Hello):
                _fail("the step did not start with hello")
            if event.version > PROTOCOL:
                _fail(f"the step speaks protocol {event.version}, this worker reads up to {PROTOCOL}")
            self._started = True
            return
        self._take(event)

    def _take(self, event: Event) -> None:
        match event:
            case Tool(id, name, summary):
                self._calls[id] = len(self.tools)
                self.tools.append(ToolEvent(name, summary))
            case ToolResult(id, True, note) if id in self._calls:
                index = self._calls[id]
                self.tools[index] = replace(self.tools[index], ok=False, note=note)
            case Audit(n):
                self.audits = max(self.audits, n)
            case Result() as done:
                self.result = done
            case Check() as done:
                self.check = done
            case Exit() as done:
                self.exit = done
            case _:
                pass

    def failure(self) -> str:
        """Why the step did not end well, in a line with no secret in it; empty when it ended cleanly.

        A step whose agent reported an error is not decided here: the agent's own words are the better message.
        """
        if self.exit is None:
            return "the step's stream ended without an exit: the container stopped or the connection broke"
        if self.exit.reason:
            return REASONS.get(self.exit.reason, f"the step ended: {self.exit.reason[:40]}")
        if not self._started:
            code = self.exit.code
            return f"the step ended before it said hello (exit code {code}): it wrote nothing the worker could read"
        said = self.result is not None or self.check is not None
        if self.exit.code != 0 and not said:
            return f"the step exited with code {self.exit.code} and no result"
        if not said:
            return "the step exited without a result"
        return ""
