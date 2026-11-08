import pytest

from shelf.domain.access import AccessRules, is_admin, may_act_from_github, may_sign_in
from shelf.domain.config import RepoConfig, Role, may_decide
from shelf.domain.model import Identity, RepoRef
from shelf.domain.pipeline import Phase
from shelf.domain.result import Err, Ok, map_ok

ALICE = Identity("alice", frozenset({"acme"}))


def test_an_instance_that_lists_nobody_lets_nobody_in() -> None:
    assert not may_sign_in(AccessRules(), ALICE)


@pytest.mark.parametrize(
    ("login", "association", "owner", "expected"),
    [
        ("alice", "NONE", "x", True),
        ("root", "NONE", "x", True),
        ("bob", "MEMBER", "acme", True),
        ("bob", "OWNER", "acme", True),
        ("bob", "COLLABORATOR", "acme", False),
        ("bob", "MEMBER", "other", False),
        ("mallory", "NONE", "acme", False),
    ],
)
def test_a_commenter_acts_only_when_the_access_list_names_them(
    login: str, association: str, owner: str, *, expected: bool
) -> None:
    rules = AccessRules(organisations=frozenset({"acme"}), users=frozenset({"alice"}), admins=frozenset({"root"}))
    assert may_act_from_github(rules, login, association, owner) is expected


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        (AccessRules(users=frozenset({"alice"})), True),
        (AccessRules(users=frozenset({"bob"})), False),
        (AccessRules(organisations=frozenset({"acme"})), True),
        (AccessRules(organisations=frozenset({"other"})), False),
        (AccessRules(users=frozenset({"bob"}), organisations=frozenset({"acme"})), True),
        (AccessRules(users=frozenset({"bob"}), admins=frozenset({"alice"})), True),
    ],
)
def test_a_restricted_instance_lets_in_listed_users_admins_and_organisation_members(
    rules: AccessRules, *, expected: bool
) -> None:
    assert may_sign_in(rules, ALICE) is expected


def test_admins_are_recognised() -> None:
    assert is_admin(AccessRules(admins=frozenset({"alice"})), "alice")
    assert not is_admin(AccessRules(), "alice")


def test_without_roles_anyone_may_decide() -> None:
    assert may_decide(RepoConfig(), "bob", Phase.SPEC_APPROVAL)


def test_with_roles_only_the_role_of_the_gate_may_decide() -> None:
    config = RepoConfig(roles={Role.PRODUCT_OWNER: frozenset({"carol"}), Role.DEVELOPER: frozenset({"dan"})})
    assert may_decide(config, "carol", Phase.SPEC_APPROVAL)
    assert not may_decide(config, "dan", Phase.SPEC_APPROVAL)
    assert may_decide(config, "dan", Phase.PULL_REQUEST)


def test_a_phase_without_a_listed_role_is_open_to_members_only() -> None:
    config = RepoConfig(roles={Role.DEVELOPER: frozenset({"dan"})})
    assert may_decide(config, "dan", Phase.IMPLEMENT)
    assert not may_decide(config, "eve", Phase.IMPLEMENT)


def test_an_administrator_may_decide_anything() -> None:
    config = RepoConfig(roles={Role.DEVELOPER: frozenset({"dan"})})
    assert may_decide(config, "root", Phase.SPEC_APPROVAL, admin=True)


def test_a_repository_name_round_trips() -> None:
    assert RepoRef.parse("acme/shop") == RepoRef("acme", "shop")
    assert RepoRef("acme", "shop").full_name == "acme/shop"


@pytest.mark.parametrize("bad", ["", "acme", "acme/", "/shop", "a/b/c"])
def test_a_malformed_repository_name_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="not a repository name"):
        RepoRef.parse(bad)


def test_map_ok_changes_a_success_and_keeps_a_failure() -> None:
    assert map_ok(Ok(2), lambda n: n * 2) == Ok(4)
    assert map_ok(Err("no"), lambda n: n) == Err("no")
