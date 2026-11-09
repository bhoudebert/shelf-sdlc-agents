from collections.abc import Sequence
from dataclasses import dataclass, field

from shelf.adapters.caching.forge import CachedForge
from shelf.domain.model import Identity, PullInfo, RepoRef

REPO = RepoRef("acme", "shop")


@dataclass
class CountingForge:
    calls: dict[str, int] = field(default_factory=dict[str, int])

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    async def exchange_code(self, code: str) -> str:
        self._count("exchange")
        return f"token-{code}"

    async def identity(self, user_token: str) -> Identity:
        self._count("identity")
        return Identity(user_token)

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        self._count("repositories")
        return [REPO]

    async def pull_request(self, user_token: str, repo: RepoRef, number: int) -> PullInfo | None:
        self._count("pull_request")
        return None


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_repositories_are_asked_once_while_the_answer_is_fresh() -> None:
    inner, clock = CountingForge(), Clock()
    forge = CachedForge(inner, ttl_seconds=60, clock=clock)
    for _ in range(5):
        assert await forge.repositories("tok") == [REPO]
    assert inner.calls["repositories"] == 1


async def test_repositories_are_asked_again_when_the_answer_is_old() -> None:
    inner, clock = CountingForge(), Clock()
    forge = CachedForge(inner, ttl_seconds=60, clock=clock)
    await forge.repositories("tok")
    clock.now = 61
    await forge.repositories("tok")
    assert inner.calls["repositories"] == 2


async def test_two_people_never_share_an_answer() -> None:
    inner = CountingForge()
    forge = CachedForge(inner, clock=Clock())
    await forge.repositories("alice-token")
    await forge.repositories("bob-token")
    assert inner.calls["repositories"] == 2


async def test_identity_is_cached_and_sign_in_never_is() -> None:
    inner = CountingForge()
    forge = CachedForge(inner, clock=Clock())
    await forge.identity("tok")
    await forge.identity("tok")
    await forge.exchange_code("a")
    await forge.exchange_code("a")
    assert (inner.calls["identity"], inner.calls["exchange"]) == (1, 2)


async def test_documents_are_read_once_while_fresh_and_again_when_old() -> None:
    from collections.abc import Mapping  # noqa: PLC0415

    from shelf.adapters.caching.documents import CachedDocuments  # noqa: PLC0415
    from shelf.domain.model import WorkId  # noqa: PLC0415

    class Counting:
        reads = 0

        async def read(self, repo: RepoRef, work_id: WorkId) -> Mapping[str, str]:
            Counting.reads += 1
            return {"spec.md": "x"}

    clock = Clock()
    cached = CachedDocuments(Counting(), ttl_seconds=10, clock=clock)
    for _ in range(3):
        await cached.read(REPO, WorkId("work-1"))
    assert Counting.reads == 1
    clock.now = 11
    await cached.read(REPO, WorkId("work-1"))
    assert Counting.reads == 2


async def test_whether_a_pull_request_exists_is_never_cached() -> None:
    inner = CountingForge()
    forge = CachedForge(inner)
    await forge.pull_request("tok", REPO, 2)
    await forge.pull_request("tok", REPO, 2)
    assert inner.calls["pull_request"] == 2
