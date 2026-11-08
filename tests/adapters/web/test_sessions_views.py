from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from shelf.adapters.web.sessions import LIFETIME, SessionStore
from shelf.adapters.web.views import Status, decision_options, entry_options, item_view, timeline
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
