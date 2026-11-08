import pytest

from shelf.domain.model import WorkId
from shelf.domain.pipeline import KIND, Kind, Phase
from shelf.domain.roles import READ_GIT, REVIEWERS, ROLES, documents_dir
from shelf.domain.verdict import parse_verdict
from shelf.domain.work import Reviewed, Verdict


def test_every_phase_an_agent_carries_out_has_a_role_and_the_others_do_not() -> None:
    agent_kinds = {Kind.PRODUCE, Kind.REVIEW}
    assert {p for p in Phase if KIND[p] in agent_kinds} == set(ROLES)


def test_reviewers_may_only_read_and_look_at_history_with_git() -> None:
    for phase in REVIEWERS:
        assert set(ROLES[phase].tools) <= {"Read", "Glob", "Grep", *READ_GIT}
        assert "Bash" not in ROLES[phase].tools


def test_a_reviewer_told_to_run_git_diff_can_run_it() -> None:
    reviewer = ROLES[Phase.CODE_REVIEW]
    assert "Bash(git diff:*)" in reviewer.tools
    assert "Bash(git log:*)" in reviewer.tools


def test_a_read_only_git_command_can_never_change_anything() -> None:
    for pattern in READ_GIT:
        assert pattern.split("(")[1].split(":")[0] in {
            "git diff",
            "git log",
            "git show",
            "git status",
            "git blame",
            "git ls-files",
        }


def test_only_the_implementer_may_run_arbitrary_commands() -> None:
    assert [p for p, r in ROLES.items() if "Bash" in r.tools] == [Phase.IMPLEMENT]


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
