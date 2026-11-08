import pytest

from shelf.domain.model import WorkId
from shelf.domain.pipeline import KIND, Kind, Phase
from shelf.domain.roles import ROLES, TITLER, documents_dir
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import Reviewed, Verdict


def test_every_phase_an_agent_carries_out_has_a_role_and_the_others_do_not() -> None:
    agent_kinds = {Kind.PRODUCE, Kind.REVIEW}
    assert {p for p in Phase if KIND[p] in agent_kinds} == set(ROLES)


def test_every_agent_has_the_normal_toolset_including_a_shell() -> None:
    for role in (*ROLES.values(), TITLER):
        assert {"Read", "Glob", "Grep", "Write", "Edit", "Bash"} == set(role.tools)


def test_each_document_is_written_by_exactly_one_role() -> None:
    documents = [r.document for r in ROLES.values() if r.document]
    assert sorted(documents) == ["design.md", "plan.md", "spec.md"]


def test_documents_live_under_the_work_id() -> None:
    assert documents_dir(WorkId("work-1")) == "docs/shelf/work-1"


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Looks good.\nVERDICT: APPROVE", Reviewed(Verdict.APPROVE, "Looks good.")),
        ("1. Missing test\nVERDICT: CHANGES\n", Reviewed(Verdict.CHANGES, "1. Missing test")),
        ("Unsure.\n  verdict: escalate  ", Reviewed(Verdict.ESCALATE, "Unsure.")),
        (
            "VERDICT: CHANGES\nthen I changed my mind\nVERDICT: APPROVE",
            Reviewed(Verdict.APPROVE, "VERDICT: CHANGES\nthen I changed my mind"),
        ),
    ],
)
def test_the_last_verdict_line_decides(answer: str, expected: Reviewed) -> None:
    assert parse_verdict(answer) == expected


def test_a_reviewer_without_a_verdict_is_never_taken_as_approving() -> None:
    reviewed = parse_verdict("I think it is fine")
    assert reviewed.verdict is Verdict.ESCALATE
    assert "no verdict" in reviewed.issues
    assert "I think it is fine" in reviewed.issues
