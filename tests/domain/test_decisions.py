from shelf.domain.config import RepoConfig, Role
from shelf.domain.decisions import HEADER, DecisionRecord, acted_as, append_entry, render_entry
from shelf.domain.pipeline import Phase
from shelf.domain.work import DecisionKind

AT = "2026-11-15T10:00:00+00:00"


def test_an_approval_of_the_spec_says_who_what_and_when() -> None:
    entry = render_entry(DecisionRecord(AT, "alice", DecisionKind.APPROVE, Phase.SPEC_APPROVAL))
    assert entry.splitlines()[0] == f"## {AT} · alice approved the spec"


def test_each_kind_of_decision_reads_as_a_sentence() -> None:
    def first(kind: DecisionKind, phase: Phase) -> str:
        return render_entry(DecisionRecord(AT, "u", kind, phase)).splitlines()[0]

    assert first(DecisionKind.CHANGES, Phase.DESIGN_REVIEW).endswith("u asked for changes to the design")
    assert first(DecisionKind.RESUME, Phase.IMPLEMENT).endswith("u resumed the work at implement")
    assert first(DecisionKind.REJECT, Phase.PULL_REQUEST).endswith("u rejected the work at pull request")
    assert first(DecisionKind.ABORT, Phase.PLAN).endswith("u aborted the work at plan")


def test_the_role_and_the_note_are_in_the_entry_in_full() -> None:
    entry = render_entry(
        DecisionRecord(AT, "bob", DecisionKind.CHANGES, Phase.DESIGN_REVIEW, "Too much.\n\nCut R10.", "tech_lead")
    )
    assert "- Acting as: tech_lead" in entry
    assert "  > Too much.\n  >\n  > Cut R10." in entry


def test_entries_are_added_in_order_and_the_log_starts_with_its_header() -> None:
    first = DecisionRecord(AT, "alice", DecisionKind.APPROVE, Phase.SPEC_APPROVAL)
    second = DecisionRecord("2026-11-15T11:00:00+00:00", "bob", DecisionKind.APPROVE, Phase.PULL_REQUEST)
    log = append_entry(append_entry("", first), second)
    assert log.startswith(HEADER)
    assert log.index("alice approved") < log.index("bob approved")
    assert log.endswith("\n")
    assert not log.endswith("\n\n")
    assert append_entry(log, first).count("alice approved") == 2, "nothing rewrites or removes an entry"


def test_a_repository_without_roles_has_no_role_to_name() -> None:
    assert acted_as(RepoConfig(), "alice", Phase.SPEC_APPROVAL, admin=False) == ""


def test_a_person_acts_in_the_role_the_step_needs() -> None:
    config = RepoConfig(roles={Role.PRODUCT_OWNER: frozenset({"maria"}), Role.TECH_LEAD: frozenset({"bob"})})
    assert acted_as(config, "maria", Phase.SPEC_APPROVAL, admin=False) == "product_owner"
    assert acted_as(config, "bob", Phase.DESIGN_REVIEW, admin=False) == "tech_lead"


def test_a_person_with_a_role_of_another_step_is_recorded_as_such() -> None:
    config = RepoConfig(roles={Role.DEVELOPER: frozenset({"dan"})})
    assert acted_as(config, "dan", Phase.SPEC_APPROVAL, admin=False) == "developer (not a role of this step)"


def test_an_administrator_and_a_person_without_a_role_are_named_as_such() -> None:
    config = RepoConfig(roles={Role.TECH_LEAD: frozenset({"bob"})})
    assert acted_as(config, "root", Phase.SPEC_APPROVAL, admin=True) == "administrator"
    assert acted_as(config, "zoe", Phase.SPEC_APPROVAL, admin=False) == "no role"
