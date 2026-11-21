import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shelf.domain.runlog import ToolEvent
from shelf.domain.stepstream import (
    PROTOCOL,
    Audit,
    Check,
    Event,
    Exit,
    Hello,
    Ping,
    Result,
    StepStream,
    StreamError,
    Tool,
    ToolResult,
    decode,
    encode,
)
from shelf.domain.usage import Usage

USAGE = Usage(10, 20, 30, 40, 0.5, 3, 12.5, ("m1", "m2"))
EVENTS: list[Event] = [
    Hello(),
    Tool("t1", "Bash", "mvn -q verify"),
    ToolResult("t1", True, "[ERROR] boom"),
    Audit(17),
    Result(
        is_error=False,
        result="done",
        session="s-1",
        usage=USAGE,
        subtype="success",
        stop_reason="end_turn",
        terminal_reason="",
        api_error_status=None,
        errors=("e1",),
        denials=("Bash: curl http://x",),
    ),
    Check(1, "[ERROR] Tests run: 3, Failures: 1"),
    Ping(),
    Exit(0),
    Exit(-1, "timeout"),
]


def lines(*events: Event) -> list[str]:
    return [encode(event) for event in events]


def feed(stream: StepStream, raw: list[str]) -> StepStream:
    for line in raw:
        stream.feed(line)
    return stream


@pytest.mark.parametrize("event", EVENTS, ids=lambda event: type(event).__name__)
def test_every_event_survives_the_wire(event: Event) -> None:
    assert decode(encode(event)) == event


@given(
    st.text(max_size=40),
    st.text(max_size=40),
    st.integers(0, 10**6),
    st.one_of(st.none(), st.floats(0, 100, allow_nan=False)),
)
def test_a_result_survives_the_wire_whatever_it_says(text: str, session: str, tokens: int, cost: float | None) -> None:
    event = Result(result=text, session=session, usage=Usage(input_tokens=tokens, cost_usd=cost))
    back = decode(encode(event))
    assert isinstance(back, Result)
    assert (back.usage.input_tokens, back.usage.cost_usd, back.session) == (tokens, cost, session) or "[redacted]" in (
        back.result
    )


def test_the_stream_says_which_protocol_it_speaks() -> None:
    assert json.loads(encode(Hello()))["v"] == PROTOCOL


def test_a_stream_adds_up_to_the_tool_calls_and_the_result() -> None:
    stream = feed(
        StepStream(),
        lines(
            Hello(),
            Tool("a", "Read", "src/x.py"),
            Tool("b", "Bash", "mvn verify"),
            ToolResult("b", True, "[ERROR] boom"),
            Tool("c", "Edit", "src/x.py"),
            ToolResult("c", False, ""),
            Audit(3),
            Ping(),
            Result(result="done", session="s", usage=USAGE),
            Exit(0),
        ),
    )
    assert stream.tools == [
        ToolEvent("Read", "src/x.py"),
        ToolEvent("Bash", "mvn verify", ok=False, note="[ERROR] boom"),
        ToolEvent("Edit", "src/x.py"),
    ]
    assert (stream.audits, stream.result and stream.result.result, stream.failure()) == (3, "done", "")


def test_a_field_or_a_kind_the_reader_does_not_know_is_ignored() -> None:
    extra = json.dumps({"e": "tool", "id": "a", "name": "Read", "summary": "x", "added_later": [1, 2]})
    future = json.dumps({"e": "thinking", "text": "hmm"})
    stream = feed(StepStream(), [encode(Hello()), extra, future, encode(Result(result="ok")), encode(Exit(0))])
    assert stream.tools == [ToolEvent("Read", "x")]
    assert stream.failure() == ""


def test_a_stream_that_stops_without_an_exit_is_a_failure() -> None:
    stream = feed(StepStream(), lines(Hello(), Result(result="done")))
    assert "without an exit" in stream.failure()


@pytest.mark.parametrize(
    ("reason", "words"), [("timeout", "out of time"), ("killed", "stopped"), ("oom", "out of memory")]
)
def test_a_timeout_is_named_and_not_called_a_failure_of_the_agent(reason: str, words: str) -> None:
    stream = feed(StepStream(), lines(Hello(), Result(result="partial"), Exit(-1, reason)))
    assert words in stream.failure()


def test_an_exit_with_an_error_code_and_no_result_says_so() -> None:
    assert "code 137" in feed(StepStream(), lines(Hello(), Exit(137))).failure()
    assert "without a result" in feed(StepStream(), lines(Hello(), Exit(0))).failure()


def test_a_line_that_is_not_json_fails_without_repeating_it() -> None:
    with pytest.raises(StreamError) as caught:
        StepStream().feed("ghp_abcdefghijklmnopqrstuvwx is the token")
    assert "ghp_" not in str(caught.value)


@pytest.mark.parametrize("line", ["[]", '"x"', '{"no":"kind"}', '{"e":1}'])
def test_a_line_with_no_kind_is_a_protocol_error(line: str) -> None:
    with pytest.raises(StreamError):
        decode(line)


def test_a_known_kind_with_the_wrong_shape_is_a_protocol_error() -> None:
    with pytest.raises(StreamError):
        decode('{"e":"audit","n":"many"}')
    with pytest.raises(StreamError):
        decode('{"e":"result","usage":[]}')


def test_the_stream_must_start_with_hello() -> None:
    with pytest.raises(StreamError, match="hello"):
        StepStream().feed(encode(Tool("a", "Read", "x")))


def test_a_newer_protocol_is_refused_and_an_older_one_is_read() -> None:
    with pytest.raises(StreamError, match="protocol 99"):
        StepStream().feed(encode(Hello(99)))
    StepStream().feed(encode(Hello(PROTOCOL)))


def test_nothing_may_follow_the_exit() -> None:
    stream = feed(StepStream(), lines(Hello(), Exit(0)))
    with pytest.raises(StreamError, match="after it had exited"):
        stream.feed(encode(Ping()))


def test_a_secret_a_sender_forgot_to_hide_is_hidden_on_arrival() -> None:
    token = "ghp_" + "a" * 30
    stream = feed(
        StepStream(),
        lines(Hello(), Tool("a", "Bash", f"git push https://{token}@x"), ToolResult("a", True, f"bad {token}")),
    )
    assert token not in repr(stream.tools)


def test_blank_lines_are_skipped() -> None:
    stream = feed(StepStream(), ["", encode(Hello()), "  ", encode(Exit(0))])
    assert stream.exit == Exit(0)


def test_a_check_ends_well_with_its_line_and_the_exit_even_when_the_command_failed() -> None:
    stream = feed(StepStream(), lines(Hello(), Check(2, "boom"), Exit(0)))
    assert stream.check == Check(2, "boom")
    assert stream.failure() == ""


def test_a_check_that_ran_out_of_time_is_named_and_has_no_line() -> None:
    stream = feed(StepStream(), lines(Hello(), Exit(-1, "timeout")))
    assert stream.check is None
    assert "ran out of time" in stream.failure()


def test_a_step_that_exits_with_neither_a_result_nor_a_check_line_is_a_failure() -> None:
    assert "without a result" in feed(StepStream(), lines(Hello(), Exit(0))).failure()


def test_the_output_of_a_check_is_hidden_on_arrival_when_it_holds_a_secret() -> None:
    token = "ghp_" + "a" * 30
    stream = feed(StepStream(), lines(Hello(), Check(1, f"remote: https://{token}@github.com"), Exit(0)))
    assert stream.check is not None
    assert token not in stream.check.output


def test_a_check_line_with_the_wrong_shape_is_a_protocol_error() -> None:
    with pytest.raises(StreamError, match="code"):
        decode('{"e":"check","code":"one","output":""}')


def test_a_step_that_ends_before_it_says_hello_is_reported_as_ended_and_not_as_a_protocol_error() -> None:
    stream = feed(StepStream(), lines(Exit(1)))

    assert "ended before it said hello" in stream.failure()
    assert "exit code 1" in stream.failure()


def test_a_step_that_was_stopped_before_hello_says_why_it_was_stopped() -> None:
    assert "ran out of time" in feed(StepStream(), lines(Exit(-1, "timeout"))).failure()


def test_a_step_that_speaks_before_hello_is_still_a_protocol_error() -> None:
    with pytest.raises(StreamError, match="hello"):
        feed(StepStream(), lines(Tool("a", "Bash", "x")))
