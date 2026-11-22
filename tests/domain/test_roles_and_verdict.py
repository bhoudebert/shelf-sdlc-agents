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
    assert documents_dir(WorkId("work-1")) == ".shelf/work-1"


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


def test_the_code_reviewer_is_told_to_send_back_what_the_author_can_still_fix() -> None:
    from shelf.adapters.claude_agent.prompts import load_prompt  # noqa: PLC0415

    prompt = load_prompt("code_reviewer")
    assert "Approve only when nothing is left that the author could fix" in prompt
    assert "`CHANGES`, not an approval with" in prompt


def test_the_developer_ends_on_the_gate_and_cannot_lean_on_a_label() -> None:
    from shelf.adapters.claude_agent.prompts import load_prompt  # noqa: PLC0415

    prompt = load_prompt("implementer")
    assert "Your last command, after your final edit, is the repository's own gate" in prompt
    assert "you cannot set a label" in prompt


def test_a_reviewer_says_where_it_stands_on_its_earlier_points() -> None:
    from shelf.domain.verdict import parse_verdict  # noqa: PLC0415

    found = parse_verdict("One point is back.\nREPEATED: 2\nBLOCKING: no\nVERDICT: CHANGES")
    assert (found.repeated, found.blocking) == (2, False)
    assert "REPEATED" in found.issues


def test_a_reviewer_that_says_nothing_of_them_has_repeated_nothing_and_blocks() -> None:
    from shelf.domain.verdict import parse_verdict  # noqa: PLC0415

    found = parse_verdict("Fine.\nVERDICT: CHANGES")
    assert (found.repeated, found.blocking) == (0, True)


def test_outside_facts_carry_their_source_through_the_four_roles() -> None:
    from shelf.adapters.claude_agent.prompts import load_prompt  # noqa: PLC0415

    for role in ("architect", "design_reviewer", "implementer", "code_reviewer"):
        assert "Outside facts" in load_prompt(role) or "outside facts" in load_prompt(role)
    assert "UNVERIFIED" in load_prompt("architect")


def test_the_developer_fixes_what_a_reviewer_finds_on_its_work() -> None:
    from shelf.adapters.claude_agent.prompts import load_prompt  # noqa: PLC0415

    prompt = load_prompt("implementer")
    assert "is in scope even if the plan did not list it" in prompt
    assert "Never answer that the file is not yours" in prompt


def test_the_code_reviewer_does_not_approve_a_proof_that_stayed_green() -> None:
    from shelf.adapters.claude_agent.prompts import load_prompt  # noqa: PLC0415

    prompt = load_prompt("code_reviewer")
    assert "stayed green, the case does not guard what it claims" in prompt
    assert "say which proof you ran and which you could not" in prompt
