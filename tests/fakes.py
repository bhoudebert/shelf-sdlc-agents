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

    async def exchange_code(self, code: str) -> str:
        return f"token-{code}"

    async def identity(self, user_token: str) -> Identity:
        return self.identities[user_token]

    async def repositories(self, user_token: str) -> Sequence[RepoRef]:
        return self.repos.get(user_token, ())


@dataclass
class FakeRunner:
    views: dict[WorkId, WorkView] = field(default_factory=dict[WorkId, WorkView])
    decisions: list[tuple[WorkId, PersonDecided]] = field(default_factory=list[tuple[WorkId, PersonDecided]])

    async def start(self, request: WorkRequest) -> WorkId:
        work_id = WorkId(f"work-{len(self.views) + 1}")
        self.views[work_id] = WorkView(work_id, request.repo, request.requester, request.entry, Phase.INTAKE)
        return work_id

    async def decide(self, work_id: WorkId, decision: PersonDecided) -> None:
        self.decisions.append((work_id, decision))

    async def view(self, work_id: WorkId) -> WorkView | None:
        return self.views.get(work_id)

    async def list(self, repos: Collection[RepoRef]) -> Sequence[WorkView]:
        return [v for v in self.views.values() if v.repo in repos]


@dataclass
class FakeConfigs:
    by_repo: dict[RepoRef, RepoConfig] = field(default_factory=dict[RepoRef, RepoConfig])

    async def load(self, repo: RepoRef) -> RepoConfig:
        return self.by_repo.get(repo, RepoConfig())
