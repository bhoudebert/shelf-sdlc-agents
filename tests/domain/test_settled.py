from shelf.domain.settled import Line, Settled, markdown_of, settled_of
from shelf.domain.story import Message, Voice, open_points_comment

LOG = """# Decisions

Who decided what.

## 2026-11-22T10:00:00+00:00 · arbitrator settled the disagreement at design review: overrule

> no evidence in the files
> the limit is in R2

## 2026-11-22T10:05:00+00:00 · alice approved the design

- Acting as: administrator

## 2026-11-22T10:09:00+00:00 · arbitrator settled the disagreement at spec review: fix

> two sentences were stale

## 2026-11-22T10:10:00+00:00 · arbitrator settled the disagreement at code review: escalate

> choose 10 or 50
"""
DESIGN = "# Design\n\n## Approach\n\nText.\n\n## Assumptions\n\n- The limit is 50.\n- Dates are UTC.\n\n## Files\n\nx\n"


def test_an_overrule_is_listed_first_and_marked_to_check() -> None:
    settled = settled_of({"decisions.md": LOG}, [])
    first = settled.lines[0]
    assert (first.kind, first.where, first.check) == ("overruled", "design review", True)
    assert first.why == "no evidence in the files the limit is in R2"


def test_a_fix_is_listed_and_not_marked() -> None:
    settled = settled_of({"decisions.md": LOG}, [])
    fixed = [line for line in settled.lines if line.kind == "fixed"]
    assert [(line.where, line.check) for line in fixed] == [("spec review", False)]


def test_an_escalation_is_not_listed_because_a_person_settled_it() -> None:
    settled = settled_of({"decisions.md": LOG}, [])
    assert all(line.where != "code review" for line in settled.lines)


def test_a_person_s_own_decisions_are_not_listed() -> None:
    settled = settled_of({"decisions.md": LOG}, [])
    assert all("alice" not in line.why for line in settled.lines)


def test_a_disagreement_the_work_went_on_past_is_listed_and_marked() -> None:
    body = open_points_comment("work-1", "design_reviewer", "design review", "1. the limit is not defined")
    settled = settled_of({}, [Message(Voice.AGENT, "Design reviewer", body)])
    assert settled.lines == (Line("passed", "design review", "1. the limit is not defined", check=True),)


def test_what_agents_assumed_is_listed_by_document() -> None:
    settled = settled_of({"design.md": DESIGN}, [])
    assert [(line.kind, line.where, line.why, line.check) for line in settled.lines] == [
        ("assumed", "design.md", "The limit is 50.", False),
        ("assumed", "design.md", "Dates are UTC.", False),
    ]


def test_an_order_that_asks_for_a_look_first() -> None:
    body = open_points_comment("work-1", "spec_critic", "spec review", "x")
    settled = settled_of({"decisions.md": LOG, "design.md": DESIGN}, [Message(Voice.AGENT, "Spec reviewer", body)])
    assert [line.kind for line in settled.lines] == ["overruled", "passed", "fixed", "assumed", "assumed"]
    assert len(settled.to_check) == 2


def test_nothing_settled_says_so() -> None:
    assert not settled_of({}, [])
    assert "nothing" in markdown_of(Settled()).lower()


def test_the_comment_marks_what_to_check() -> None:
    text = markdown_of(settled_of({"decisions.md": LOG, "design.md": DESIGN}, []))
    assert text.startswith("**Settled without you**")
    assert "1 to check before you merge" in text
    assert "- ⚠️ The arbitrator **overruled** the reviewer at the design review: no evidence" in text
    assert "- An agent **assumed** (in `design.md`): The limit is 50." in text
