import pytest

from shelf.domain.model import WorkId
from shelf.domain.pipeline import Phase
from shelf.domain.results import Conflicts, Results, results_note
from shelf.domain.roles import documents_dir, legacy_documents_dir


def test_a_run_keeps_its_files_in_the_shelf_folder_and_older_ones_are_still_known() -> None:
    assert documents_dir(WorkId("work-1")) == ".shelf/work-1"
    assert legacy_documents_dir(WorkId("work-1")) == "docs/shelf/work-1"


def test_the_architect_writes_the_repositorys_specs_after_the_spec_is_approved() -> None:
    note = results_note(Results(), Phase.DESIGN)
    assert "has been approved" in note
    assert "`openspec/specs/`" in note
    assert "does not exist, create it" in note


def test_the_spec_writer_and_reviewer_are_told_nothing_about_the_repositorys_specs() -> None:
    assert results_note(Results(), Phase.INTAKE) == ""
    assert results_note(Results(), Phase.SPEC_REVIEW) == ""


def test_the_architect_is_told_where_decision_records_go_and_how_to_replace_one() -> None:
    note = results_note(Results(decisions="docs/decisions"), Phase.DESIGN)
    assert "`docs/decisions/`" in note
    assert "Supersedes: NNNN" in note
    assert "superseded by NNNN" in note


def test_the_design_reviewer_refuses_an_unstated_contradiction_by_default() -> None:
    note = results_note(Results(), Phase.DESIGN_REVIEW)
    assert "every earlier accepted record in `docs/adr/`" in note
    assert "Do not approve it" in note


def test_a_warning_setting_reports_the_contradiction_without_asking_for_changes() -> None:
    note = results_note(Results(conflicts=Conflicts.WARN), Phase.DESIGN_REVIEW)
    assert "do not ask for changes" in note


def test_the_conflict_check_can_be_switched_off() -> None:
    assert results_note(Results(conflicts=Conflicts.OFF), Phase.DESIGN_REVIEW) == ""


def test_a_repository_that_wants_no_records_gets_no_record_instructions() -> None:
    results = Results(write=frozenset({"spec"}))
    assert "decision" not in results_note(results, Phase.DESIGN)
    assert results_note(results, Phase.DESIGN_REVIEW) == ""
    assert "`openspec/specs/`" in results_note(results, Phase.DESIGN)


@pytest.mark.parametrize("phase", [Phase.PLAN, Phase.IMPLEMENT, Phase.VERIFY])
def test_the_other_phases_are_told_nothing(phase: Phase) -> None:
    assert results_note(Results(), phase) == ""
