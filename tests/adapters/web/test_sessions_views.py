from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from shelf.adapters.web.sessions import LIFETIME, SessionStore
from shelf.adapters.web.views import (
    Status,
    ago,
    decision_options,
    document_views,
    entry_options,
    item_view,
    render_markdown,
    timeline,
    webhook_status,
)
from shelf.domain.model import Identity, RepoRef, WorkId, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.work import Outcome, Reason

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
WORK = WorkView(WorkId("work-1"), RepoRef("acme", "shop"), "alice", EntryPoint.NEED, Phase.DESIGN)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def test_a_session_lives_until_the_token_would_expire() -> None:
    clock = Clock()
    store = SessionStore(clock)
    session_id = store.create(Identity("alice"), "tok")
    clock.now = NOW + LIFETIME - timedelta(seconds=1)
    assert store.get(session_id) is not None
    clock.now = NOW + LIFETIME
    assert store.get(session_id) is None


def test_ending_or_missing_sessions_are_harmless() -> None:
    store = SessionStore()
    session_id = store.create(Identity("alice"), "tok")
    store.end(session_id)
    store.end(None)
    assert store.get(session_id) is None
    assert store.get(None) is None


def test_every_session_id_is_different() -> None:
    store = SessionStore()
    assert store.create(Identity("a"), "t") != store.create(Identity("a"), "t")


def test_a_card_says_what_the_work_waits_for() -> None:
    waiting = item_view(_with(waiting_for=Reason.GATE))
    assert (waiting.status, waiting.waiting, waiting.phase) == (Status.WAITING, "Waiting for your approval", "Design")
    assert item_view(WORK).status is Status.RUNNING
    done = item_view(_with(outcome=Outcome.MERGED))
    assert (done.status, done.outcome) == (Status.DONE, "Merged")


def _with(**changes: Any) -> WorkView:
    return replace(WORK, **changes)


def test_the_timeline_marks_done_current_and_todo() -> None:
    states = [step.state for step in timeline(WORK)]
    assert states == ["done"] * 3 + ["current"] + ["todo"] * 6


def test_a_waiting_phase_is_marked_waiting_and_a_stopped_one_stopped() -> None:
    assert [s.state for s in timeline(_with(waiting_for=Reason.GATE))][3] == "waiting"
    assert [s.state for s in timeline(_with(outcome=Outcome.ABORTED))][3] == "stopped"
    assert {s.state for s in timeline(_with(phase=Phase.PULL_REQUEST, outcome=Outcome.MERGED))} == {"done"}


def test_the_start_form_lists_only_enabled_entry_points() -> None:
    options = entry_options(frozenset({EntryPoint.NEED, EntryPoint.PULL_REQUEST_REVIEW}))
    assert [o.value for o in options] == ["need", "pull_request_review"]
    assert [o.needs_pull_request for o in options] == [False, True]


def test_decision_buttons_follow_the_wait() -> None:
    assert next(d.value for d in decision_options(Reason.FAILURE)) == "resume"
    assert [d.value for d in decision_options(Reason.MERGE)] == ["changes", "reject", "abort"]
    assert decision_options(None) == []
    assert next(d for d in decision_options(Reason.GATE) if d.value == "changes").needs_note


def test_markdown_is_rendered_for_reading() -> None:
    html = str(render_markdown("# Title\n\n- one\n- two\n\n`code`"))
    assert "<h1>Title</h1>" in html
    assert "<li>one</li>" in html
    assert "<code>code</code>" in html


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "[click](javascript:alert(1))",
        "<iframe src='https://evil.example'></iframe>",
        "[x](data:text/html;base64,PHNjcmlwdD4=)",
    ],
)
def test_nothing_an_agent_writes_can_become_active_content(hostile: str) -> None:
    html = str(render_markdown(hostile)).lower()
    assert "<script" not in html
    assert "<iframe" not in html
    assert "<img" not in html
    assert 'href="javascript:' not in html
    assert "<img" not in html  # the text may appear, escaped; a tag may not


def test_tables_are_rendered_as_tables() -> None:
    html = str(render_markdown("| a | b |\n| --- | --- |\n| 1 | 2 |"))
    assert "<table>" in html
    assert "<td>1</td>" in html


def test_the_document_for_the_current_phase_is_open_and_the_others_folded() -> None:
    docs = document_views({"spec.md": "# S", "design.md": "# D", "plan.md": "# P"}, Phase.DESIGN_REVIEW)
    assert [(d.name, d.open) for d in docs] == [("spec.md", False), ("design.md", True), ("plan.md", False)]
    assert [d.title for d in docs] == ["Spec", "Design", "Plan"]


def test_a_document_not_written_yet_is_simply_absent() -> None:
    assert [d.name for d in document_views({"spec.md": "x"}, Phase.INTAKE)] == ["spec.md"]
    assert document_views({}, Phase.INTAKE) == []


def test_the_webhook_status_says_what_to_check_when_nothing_has_arrived() -> None:
    status = webhook_status(None, NOW)
    assert status.level == "warning"
    assert "Recent deliveries" in status.text


def test_the_webhook_status_for_each_kind_of_last_delivery() -> None:
    from shelf.adapters.web.webhook_log import Delivery, Result  # noqa: PLC0415

    def delivery(result: Result, detail: str = "") -> Delivery:
        return Delivery(NOW - timedelta(minutes=3), "issue_comment", result, detail)

    assert webhook_status(delivery(Result.BAD_SIGNATURE), NOW).level == "error"
    assert webhook_status(delivery(Result.REFUSED, "nope"), NOW).text.endswith("nope")
    applied = webhook_status(delivery(Result.APPLIED, "alice decided approve"), NOW)
    assert (applied.level, "3 min ago" in applied.text) == ("ok", True)
    assert webhook_status(delivery(Result.IGNORED), NOW).level == "ok"


@pytest.mark.parametrize(("seconds", "expected"), [(10, "moments ago"), (300, "5 min ago"), (7300, "2 h ago")])
def test_how_long_ago_is_said_in_a_few_words(seconds: int, expected: str) -> None:
    assert ago(NOW - timedelta(seconds=seconds), NOW) == expected


def test_a_row_says_how_long_ago_the_work_last_did_anything_and_when_exactly() -> None:
    work = replace(WORK, updated_at=(NOW - timedelta(minutes=12)).isoformat())
    card = item_view(work, NOW)
    assert card.updated == "12 min ago"
    assert card.updated_at == "8 Nov 11:48 UTC"
    assert item_view(replace(work, updated_at=(NOW - timedelta(days=3)).isoformat()), NOW).updated == "3 d ago"


def test_work_that_predates_times_shows_none() -> None:
    card = item_view(WORK, NOW)
    assert (card.updated, card.updated_at) == ("", "")


def test_the_timeline_says_when_each_step_last_did_something() -> None:
    work = replace(WORK, times=(("design", "2026-11-08T09:12:00+00:00"),))
    shown = {step.label: step.at for step in timeline(work)}
    assert shown["Design"] == "8 Nov 09:12 UTC"
    assert shown["Spec"] == ""
