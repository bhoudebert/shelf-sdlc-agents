import pytest

from shelf.application.errors import NotAllowed
from shelf.application.sign_in import sign_in
from shelf.domain.access import AccessRules
from shelf.domain.model import Identity
from shelf.domain.result import Err, Ok
from tests.fakes import FakeForge

ALICE = Identity("alice", frozenset({"acme"}))


@pytest.fixture
def forge() -> FakeForge:
    return FakeForge(identities={"token-code": ALICE})


async def test_nobody_signs_in_when_the_access_list_is_empty(forge: FakeForge) -> None:
    result = await sign_in(forge, AccessRules(), "code")
    assert isinstance(result, Err)
    assert isinstance(result.error, NotAllowed)
    assert "no access list" in result.error.reason


async def test_a_member_of_a_listed_organisation_signs_in(forge: FakeForge) -> None:
    result = await sign_in(forge, AccessRules(organisations=frozenset({"acme"})), "code")
    assert isinstance(result, Ok)


async def test_someone_outside_the_lists_is_refused(forge: FakeForge) -> None:
    result = await sign_in(forge, AccessRules(users=frozenset({"bob"})), "code")
    assert result == Err(NotAllowed("alice is not on this instance's access list"))


async def test_a_member_of_a_listed_organisation_is_let_in_even_when_github_lists_none_for_the_token() -> None:
    forge = FakeForge(identities={"token-code": Identity("hidwulf")}, members={"hidwulf": frozenset({"hid-ttt"})})
    result = await sign_in(forge, AccessRules(organisations=frozenset({"hid-ttt"})), "code")
    assert isinstance(result, Ok)
    assert result.value.identity.organisations == frozenset({"hid-ttt"})


async def test_someone_who_is_in_no_listed_organisation_is_refused_with_a_hint() -> None:
    forge = FakeForge(identities={"token-code": Identity("eve")})
    result = await sign_in(forge, AccessRules(organisations=frozenset({"hid-ttt"})), "code")
    assert isinstance(result, Err)
    assert isinstance(result.error, NotAllowed)
    assert "must be public" in result.error.reason
