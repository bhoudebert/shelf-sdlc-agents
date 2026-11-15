from shelf.domain.runlog import (
    MAX_EVENTS,
    RunRecord,
    ToolEvent,
    from_data,
    keep_events,
    redact,
    result_note,
    to_data,
    tool_summary,
)
from shelf.domain.usage import Usage


def test_a_credential_in_a_command_or_an_error_is_replaced_by_a_mark() -> None:
    for text in (
        "git clone https://x-access-token:ghp_abcdefghijklmnopqrstuvwxyz0123456789@github.com/a/b",
        "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz' https://x.example",
        "export ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwxyz",
        "DB_PASSWORD=hunter2hunter2 npm test",
        "AKIAABCDEFGHIJKLMNOP",
    ):
        cleaned = redact(text)
        assert "[redacted]" in cleaned, text
        for secret in ("ghp_abcdef", "abcdefghijklmnopqrstuvwxyz", "hunter2", "AKIAABCDEFGHIJKLMNOP"):
            assert secret not in cleaned, (secret, cleaned)
    assert redact("npm run quality") == "npm run quality"


def test_a_tool_call_is_summed_up_by_what_it_is_about_shortened_and_redacted() -> None:
    assert tool_summary("Bash", {"command": "npm  test\n  --silent"}) == "npm test --silent"
    assert tool_summary("Edit", {"file_path": "src/a.ts"}) == "src/a.ts"
    assert tool_summary("WebFetch", {"url": "https://opencode.ai/docs"}) == "https://opencode.ai/docs"
    assert tool_summary("Task", {"description": "x"}) == ""
    assert len(tool_summary("Bash", {"command": "x" * 1000})) == 160


def test_the_start_of_what_a_failed_tool_said_is_kept_from_a_text_or_from_blocks() -> None:
    assert result_note("  boom \n  here ") == "boom here"
    assert result_note([{"type": "text", "text": "line one"}, {"type": "image"}, {"text": "two"}]) == "line one two"
    assert result_note(None) == ""
    assert len(result_note("y" * 1000)) == 240


def test_a_run_that_made_too_many_calls_keeps_every_failure_first() -> None:
    events = [ToolEvent("Bash", f"cmd {n}") for n in range(MAX_EVENTS + 50)]
    events[MAX_EVENTS + 10] = ToolEvent("Bash", "the failing one", ok=False, note="exit 1")
    kept = keep_events(events)
    assert len(kept) == MAX_EVENTS
    assert any(not event.ok for event in kept)
    assert [e.summary for e in kept if not e.ok] == ["the failing one"]
    assert keep_events(events[:5]) == tuple(events[:5])


def test_a_record_survives_a_trip_through_plain_data_and_an_older_file_still_reads() -> None:
    record = RunRecord(
        "work-1",
        "implement",
        1,
        "implementer",
        "2026-11-15T15:00:00+00:00",
        "2026-11-15T15:05:00+00:00",
        "failed",
        model="m",
        usage=Usage(1, 2, 3, 4, 0.5, 6, 7.0, ("m",)),
        resumed=True,
        error="boom",
        denials=("Bash: rm -rf x",),
        tools=(ToolEvent("Bash", "npm test", ok=False, note="exit 1"),),
        tool_calls=1,
    )
    assert from_data(to_data(record)) == record
    older = from_data({"work_id": "w", "phase": "plan"})
    assert (older.work_id, older.attempt, older.tools, older.usage) == ("w", 0, (), Usage())
