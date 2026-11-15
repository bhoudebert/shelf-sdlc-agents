from shelf.domain.export import ExportStep, WorkExport, fenced, filename, render
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
