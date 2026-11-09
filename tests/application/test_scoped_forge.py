from shelf.application.scoped_forge import ScopedForge
from shelf.domain.access import AccessRules
from shelf.domain.model import Identity, RepoRef
from tests.fakes import FakeForge

LISTED = RepoRef("hid-ttt", "shop")
OWN = RepoRef("hidwulf", "notes")
STRANGER = RepoRef("stranger-org", "loot")


def scoped(rules: list[AccessRules]) -> ScopedForge:
    forge = FakeForge(
        identities={"t": Identity("hidwulf")},
        repos={"t": (LISTED, OWN, STRANGER)},
    )
    return ScopedForge(forge, lambda: rules[0])


async def test_only_repositories_of_listed_owners_or_the_persons_own_account_are_visible() -> None:
    forge = scoped([AccessRules(organisations=frozenset({"hid-ttt"}))])
    assert list(await forge.repositories("t")) == [LISTED, OWN]


async def test_an_edit_of_the_access_list_applies_at_once() -> None:
    rules = [AccessRules(organisations=frozenset({"hid-ttt"}))]
    forge = scoped(rules)
    assert STRANGER not in await forge.repositories("t")
    rules[0] = AccessRules(organisations=frozenset({"hid-ttt", "stranger-org"}))
    assert STRANGER in await forge.repositories("t")


async def test_a_pull_request_of_an_unserved_repository_does_not_exist() -> None:
    forge = scoped([AccessRules(organisations=frozenset({"hid-ttt"}))])
    assert await forge.pull_request("t", STRANGER, 1) is None
    assert await forge.pull_request("t", LISTED, 1) is not None
