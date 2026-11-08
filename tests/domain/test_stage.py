import pytest

from shelf.domain.pipeline import Phase
from shelf.domain.stage import COLORS, PREFIX, RUNNING_NAMES, Tone, stage_of
from shelf.domain.work import Reason


def test_every_phase_has_a_name() -> None:
    assert set(RUNNING_NAMES) == set(Phase)


def test_a_running_step_has_a_working_label() -> None:
    stage = stage_of(Phase.IMPLEMENT, None)
    assert stage.name == "shelf: implementing"
    assert stage.color == COLORS[Tone.WORKING]


@pytest.mark.parametrize("reason", [Reason.GATE, Reason.ESCALATION, Reason.FAILURE])
def test_waiting_for_a_person_is_labelled_with_what_they_are_asked(reason: Reason) -> None:
    stage = stage_of(Phase.SPEC_APPROVAL, reason)
    assert stage.name == "shelf: needs you: spec approval"
    assert stage.color == COLORS[Tone.WAITING]


def test_the_merge_wait_is_ready_to_merge() -> None:
    stage = stage_of(Phase.PULL_REQUEST, Reason.MERGE)
    assert stage.name == "shelf: ready to merge"
    assert stage.color == COLORS[Tone.READY]


def test_every_stage_label_carries_the_prefix_the_adapter_cleans_up_by() -> None:
    for phase in Phase:
        for reason in (None, Reason.GATE, Reason.MERGE):
            assert stage_of(phase, reason).name.startswith(PREFIX)
