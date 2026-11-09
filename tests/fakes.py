"""In-memory implementations of the ports, shared by the use-case tests."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from shelf.domain.config import RepoConfig
from shelf.domain.model import Identity, RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import Phase
from shelf.domain.work import PersonDecided


@dataclass
class FakeForge:
    identities: dict[str, Identity] = field(default_factory=dict[str, Identity])
    repos: dict[str, tuple[RepoRef, ...]] = field(default_factory=dict[str, tuple[RepoRef, ...]])

    missing_pulls: set[tuple[RepoRef, int]] = field(default_factory=set[tuple[RepoRef, int]])

    async def exchange_code(self, code: str) -> str:
        return f"token-{code}"

    async def pull_request_exists(self, user_token: str, repo: RepoRef, number: int) -> bool:
        return (repo, number) not in self.missing_pulls

    async def identity(self, user_token: str) -> Identity:
        return self.identities[user_token]

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        return self.repos.get(user_token, ())


@dataclass
class FakeRunner:
    views: dict[WorkId, WorkView] = field(default_factory=dict[WorkId, WorkView])
    decisions: list[tuple[WorkId, PersonDecided]] = field(default_factory=list[tuple[WorkId, PersonDecided]])
    closed: list[tuple[WorkId, bool]] = field(default_factory=list[tuple[WorkId, bool]])
    terminated: list[tuple[WorkId, str]] = field(default_factory=list[tuple[WorkId, str]])

    async def start(self, request: WorkRequest) -> WorkId:
        work_id = WorkId(f"work-{len(self.views) + 1}")
        self.views[work_id] = WorkView(work_id, request.repo, request.requester, request.entry, Phase.INTAKE)
        return work_id

    async def decide(self, work_id: WorkId, decision: PersonDecided) -> None:
        self.decisions.append((work_id, decision))

    async def terminate(self, work_id: WorkId, reason: str) -> None:
        self.terminated.append((work_id, reason))

    async def pull_request_closed(self, work_id: WorkId, *, merged: bool) -> None:
        self.closed.append((work_id, merged))

    async def view(self, work_id: WorkId) -> WorkView | None:
        return self.views.get(work_id)

    async def list(self, repos: Collection[RepoRef] | None) -> Sequence[WorkView]:
        return [v for v in self.views.values() if repos is None or v.repo in repos]


@dataclass
class FakeConfigs:
    by_repo: dict[RepoRef, RepoConfig] = field(default_factory=dict[RepoRef, RepoConfig])

    async def load(self, repo: RepoRef) -> RepoConfig:
        return self.by_repo.get(repo, RepoConfig())
