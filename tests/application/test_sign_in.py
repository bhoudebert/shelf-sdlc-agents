import pytest

from shelf.application.errors import NotAllowed
from shelf.application.sign_in import SignedIn, sign_in
from shelf.domain.access import AccessRules
from shelf.domain.model import Identity
from shelf.domain.result import Err, Ok
from tests.fakes import FakeForge

ALICE = Identity("alice", frozenset({"acme"}))


@pytest.fixture
def forge() -> FakeForge:
    return FakeForge(identities={"token-code": ALICE})


async def test_anyone_signs_in_on_an_open_instance(forge: FakeForge) -> None:
    assert await sign_in(forge, AccessRules(), "code") == Ok(SignedIn(ALICE, "token-code"))


async def test_a_member_of_a_listed_organisation_signs_in(forge: FakeForge) -> None:
    result = await sign_in(forge, AccessRules(organisations=frozenset({"acme"})), "code")
    assert isinstance(result, Ok)


async def test_someone_outside_the_lists_is_refused(forge: FakeForge) -> None:
    result = await sign_in(forge, AccessRules(users=frozenset({"bob"})), "code")
    assert result == Err(NotAllowed("alice is not on this instance's access list"))
