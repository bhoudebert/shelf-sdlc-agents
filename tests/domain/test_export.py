from dataclasses import replace

from shelf.domain.export import ExportStep, WorkExport, fenced, filename, in_window, render
from shelf.domain.guard import StoppedCall
from shelf.domain.runlog import RunRecord, ToolEvent
from shelf.domain.story import Message, Voice
from shelf.domain.usage import StepUsage, Usage, summarize


def test_a_fence_is_longer_than_any_run_of_backticks_inside_it() -> None:
    assert fenced("plain").startswith("```markdown\n")
    inner = fenced("a\n```bash\nx\n```\nb")
    assert inner.startswith("````markdown\n")
    assert inner.endswith("\n````")
    assert fenced("`````x`````").startswith("``````markdown")


def test_the_file_name_holds_nothing_a_header_could_trip_on() -> None:
    assert filename("work-1a2b") == "shelf-work-1a2b.md"
    assert filename('x"\r\nSet-Cookie: a') == "shelf-x___Set-Cookie__a.md"
    assert filename("") == "shelf-work.md"


def test_the_whole_conversation_is_kept_in_order_and_empty_comments_are_dropped() -> None:
    story = [Message(Voice.PERSON, f"p{n}", f"comment {n}", "2026-11-09T09:12:00Z") for n in range(80)]
    story.append(Message(Voice.AGENT, "empty", "   "))
    text = render(
        WorkExport("w", [("Repository", "acme/shop")], [ExportStep("Spec", "done")], "ask", story, {}, None, "now")
    )
    assert "### 1. p0 (person)" in text
    assert "### 80. p79 (person)" in text
    assert text.index("comment 0") < text.index("comment 79")
    assert "empty" not in text


def test_a_missing_part_and_an_empty_work_are_said() -> None:
    text = render(WorkExport("w", [], [], "", None, None, None, "now"))
    assert "_No request text was kept._" in text
    assert "conversation could not be read" in text
    assert "documents could not be read" in text
    assert "_Nothing was recorded for this work._" in text


def test_the_usage_is_totalled_per_agent_and_per_step() -> None:
    spent = Usage(input_tokens=1000, output_tokens=100, cost_usd=0.25, turns=5, seconds=9.0)
    usage = summarize(
        (StepUsage("implement", 0, "implementer", spent), StepUsage("implement", 1, "implementer", spent))
    )
    text = render(WorkExport("w", [], [], "r", [], {}, usage, "now"))
    assert "Total: 2,200 tokens" in text
    assert "| implementer | 2 | 10 | 18 | 2,200 | $0.50 |" in text
    assert "| implement | 1 | implementer |" in text


def _call(
    at: str, decision: str = "allow", intended: str = "deny", summary: str = "cat > opencode.json"
) -> "StoppedCall":
    return StoppedCall(at, "claude", "s1", "bash", decision, intended, ("tamper",), "protected file", summary)


def test_only_the_calls_made_during_the_work_are_listed_oldest_first() -> None:
    calls = [
        _call("2026-11-15T16:39:14"),
        _call("2026-11-15T15:16:57"),
        _call("2026-11-14T10:58:43", summary="before"),
        _call("2026-11-15T19:00:00", summary="after"),
    ]
    kept = in_window(calls, "2026-11-15T15:00:00+00:00", "2026-11-15T17:00:00+00:00")
    assert [c.at for c in kept] == ["2026-11-15T15:16:57", "2026-11-15T16:39:14"]
    assert len(in_window(calls, "", "")) == 4  # unknown ends: nothing is cut


def test_the_guard_section_says_stopped_or_only_recorded_and_when_nothing_was_flagged() -> None:
    base = WorkExport("w", [], [], "r", [], {}, None, "now", guard=[], started="2026-11-15T15:00:00+00:00")
    assert "flagged nothing in that time" in render(base)
    flagged = [_call("2026-11-15T16:00:00", "deny", "deny"), _call("2026-11-15T16:01:00", summary="a|b")]
    text = render(replace(base, guard=flagged))
    assert "| stopped |" in text
    assert "not stopped (recorded; the policy meant deny)" in text
    assert "a\\|b" in text  # a pipe in a command does not break the table
    assert "flagged nothing" not in text


def test_the_guard_section_warns_when_earlier_calls_may_be_missing_and_when_it_cannot_be_read() -> None:
    base = WorkExport(
        "w", [], [], "r", [], {}, None, "now", guard=[_call("2026-11-15T16:00:00")], started="2026-11-15T15:00:00+00:00"
    )
    assert "earlier ones may be missing" in render(base)
    early = replace(base, guard=[_call("2026-11-15T14:00:00")])
    assert "earlier ones may be missing" not in render(early)
    assert "The guard could not be read" in render(replace(base, guard=None))


def _run(**more: object) -> RunRecord:
    base = {
        "work_id": "w",
        "phase": "implement",
        "attempt": 1,
        "role": "implementer",
        "started": "2026-11-15T16:00:00+00:00",
        "ended": "2026-11-15T16:05:00+00:00",
        "outcome": "finished",
    }
    return RunRecord(**(base | more))  # type: ignore[arg-type]


def test_the_runs_section_lists_the_failed_commands_with_what_they_said_and_what_was_refused() -> None:
    run = _run(
        tools=(ToolEvent("Bash", "npm test"), ToolEvent("Bash", "npx prettier --check .", ok=False, note="EROFS")),
        tool_calls=2,
        denials=("Bash: cat > opencode.json",),
        setup="Tools: the worker tried to install node 24 and could not: 404",
        error="",
        usage=Usage(input_tokens=1000, turns=7, seconds=12.0),
        max_turns=40,
        resumed=True,
    )
    text = render(WorkExport("w", [], [], "r", [], {}, None, "now", runs=[run]))
    assert "## Agent runs" in text
    assert "### 1. implementer · implement, round 1 · finished" in text
    assert "| 2 | Bash | `npx prettier --check .` | FAILED: EROFS |" in text
    assert "**Tool calls:** 2, of which 1 failed" in text
    assert "`Bash: cat > opencode.json`" in text
    assert "could not: 404" in text
    assert "**Session:** continued" in text
    assert "7 of 40 turns" in text


def test_the_runs_section_says_when_no_record_exists_or_none_is_kept() -> None:
    none_kept = render(WorkExport("w", [], [], "r", [], {}, None, "now", runs=None))
    assert "keeps no record of agent runs" in none_kept
    empty = render(WorkExport("w", [], [], "r", [], {}, None, "now", runs=[]))
    assert "No run record was kept for this work" in empty
