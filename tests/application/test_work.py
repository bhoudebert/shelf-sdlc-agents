import pytest

from shelf.application.errors import Invalid, NotAllowed, NotFound
from shelf.application.work import board, decide_work, start_work
from shelf.domain.access import AccessRules
from shelf.domain.config import RepoConfig, Role
from shelf.domain.model import PullInfo, RepoRef, WorkId, WorkRequest
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.result import Err, Ok
from shelf.domain.work import DecisionKind, PersonDecided
from tests.fakes import FakeConfigs, FakeForge, FakeRunner

REPO = RepoRef("acme", "shop")
OTHER = RepoRef("acme", "secret")


@pytest.fixture
def forge() -> FakeForge:
    return FakeForge(repos={"tok": (REPO,)})


def need(repo: RepoRef = REPO, text: str = "loyalty points") -> WorkRequest:
    return WorkRequest(repo, "alice", EntryPoint.NEED, text)


async def test_work_starts_on_a_repository_the_person_can_see(forge: FakeForge) -> None:
    runner = FakeRunner()
    result = await start_work(runner, forge, FakeConfigs(), user_token="tok", request=need())
    assert result == Ok(WorkId("work-1"))


async def test_a_repository_the_person_cannot_see_is_reported_as_missing(forge: FakeForge) -> None:
    result = await start_work(FakeRunner(), forge, FakeConfigs(), user_token="tok", request=need(OTHER))
    assert result == Err(NotFound("acme/secret"))


async def test_an_entry_point_the_repository_disabled_is_refused(forge: FakeForge) -> None:
    configs = FakeConfigs({REPO: RepoConfig(entries=frozenset({EntryPoint.PULL_REQUEST_REVIEW}))})
    result = await start_work(FakeRunner(), forge, configs, user_token="tok", request=need())
    assert isinstance(result, Err)
    assert isinstance(result.error, Invalid)


async def test_an_empty_need_is_refused(forge: FakeForge) -> None:
    result = await start_work(FakeRunner(), forge, FakeConfigs(), user_token="tok", request=need(text="  "))
    assert result == Err(Invalid("the request is empty"))


async def test_reviewing_a_pull_request_needs_its_number(forge: FakeForge) -> None:
    request = WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW)
    result = await start_work(FakeRunner(), forge, FakeConfigs(), user_token="tok", request=request)
    assert isinstance(result, Err)
    assert isinstance(result.error, Invalid)


async def test_reviewing_a_pull_request_needs_no_text(forge: FakeForge) -> None:
    request = WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, pull_request=7)
    result = await start_work(FakeRunner(), forge, FakeConfigs(), user_token="tok", request=request)
    assert isinstance(result, Ok)


async def test_a_decision_reaches_the_work_when_the_person_may_make_it(forge: FakeForge) -> None:
    runner = FakeRunner()
    await start_work(runner, forge, FakeConfigs(), user_token="tok", request=need())
    result = await decide_work(
        runner, FakeConfigs(), AccessRules(), work_id=WorkId("work-1"), login="bob", kind=DecisionKind.APPROVE
    )
    assert result == Ok(None)
    assert runner.decisions == [(WorkId("work-1"), PersonDecided("bob", DecisionKind.APPROVE))]


async def test_a_decision_on_unknown_work_is_reported_as_missing() -> None:
    result = await decide_work(
        FakeRunner(),
        FakeConfigs(),
        AccessRules(),
        work_id=WorkId("nope"),
        login="bob",
        kind=DecisionKind.ABORT,
    )
    assert result == Err(NotFound("nope"))


async def test_a_person_without_the_right_role_may_not_decide(forge: FakeForge) -> None:
    runner = FakeRunner()
    await start_work(runner, forge, FakeConfigs(), user_token="tok", request=need())
    configs = FakeConfigs({REPO: RepoConfig(roles={Role.PRODUCT_OWNER: frozenset({"carol"})})})
    result = await decide_work(
        runner, configs, AccessRules(), work_id=WorkId("work-1"), login="bob", kind=DecisionKind.APPROVE
    )
    assert isinstance(result, Err)
    assert isinstance(result.error, NotAllowed)
    assert runner.decisions == []


async def test_an_administrator_may_always_decide(forge: FakeForge) -> None:
    runner = FakeRunner()
    await start_work(runner, forge, FakeConfigs(), user_token="tok", request=need())
    configs = FakeConfigs({REPO: RepoConfig(roles={Role.PRODUCT_OWNER: frozenset({"carol"})})})
    rules = AccessRules(admins=frozenset({"bob"}))
    result = await decide_work(runner, configs, rules, work_id=WorkId("work-1"), login="bob", kind=DecisionKind.ABORT)
    assert result == Ok(None)


async def test_the_board_shows_only_the_repositories_the_person_can_see(forge: FakeForge) -> None:
    runner = FakeRunner()
    await start_work(runner, forge, FakeConfigs(), user_token="tok", request=need())
    await runner.start(need(OTHER))
    views = await board(runner, forge, user_token="tok")
    assert [v.repo for v in views] == [REPO]
    assert views[0].phase is Phase.INTAKE


def everything_on(forge: FakeForge) -> FakeConfigs:
    forge.everything_exists = False
    return FakeConfigs({REPO: RepoConfig(entries=frozenset(EntryPoint))})


async def test_a_review_of_a_pull_request_the_repository_does_not_have_is_refused_with_its_name(
    forge: FakeForge,
) -> None:
    review = WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, "", 2)
    result = await start_work(FakeRunner(), forge, everything_on(forge), user_token="tok", request=review)
    assert result == Err(Invalid("acme/shop has no pull request #2: check the repository"))


async def test_a_review_of_an_existing_pull_request_starts(forge: FakeForge) -> None:
    review = WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_REVIEW, "", 2)
    config = everything_on(forge)
    forge.pulls[(REPO, 2)] = PullInfo("feat/x", "abc", open=False, same_repository=False)  # a review needs none of it
    assert isinstance(await start_work(FakeRunner(), forge, config, user_token="tok", request=review), Ok)


def work_on(text: str = "rebase it onto main", number: int | None = 2) -> WorkRequest:
    return WorkRequest(REPO, "alice", EntryPoint.PULL_REQUEST_WORK, text, number)


@pytest.mark.parametrize(
    ("pull", "refusal"),
    [
        (None, "acme/shop has no pull request #2: check the repository"),
        (PullInfo("feat/x", "abc", open=False, same_repository=True), "pull request #2 is closed"),
        (
            PullInfo("feat/x", "abc", open=True, same_repository=False),
            "pull request #2 comes from a fork: the App cannot push to its branch",
        ),
    ],
)
async def test_work_on_a_pull_request_needs_one_that_is_open_and_from_this_repository(
    forge: FakeForge, pull: PullInfo | None, refusal: str
) -> None:
    config = everything_on(forge)
    if pull is not None:
        forge.pulls[(REPO, 2)] = pull
    result = await start_work(FakeRunner(), forge, config, user_token="tok", request=work_on())
    assert result == Err(Invalid(refusal))


async def test_work_on_a_pull_request_starts_when_it_can_be_changed(forge: FakeForge) -> None:
    config = everything_on(forge)
    forge.pulls[(REPO, 2)] = PullInfo("feat/x", "abc", open=True, same_repository=True)
    assert isinstance(await start_work(FakeRunner(), forge, config, user_token="tok", request=work_on()), Ok)


async def test_work_on_a_pull_request_needs_a_number_and_something_to_do(forge: FakeForge) -> None:
    config = everything_on(forge)
    forge.pulls[(REPO, 2)] = PullInfo("feat/x", "abc", open=True, same_repository=True)
    no_number = await start_work(FakeRunner(), forge, config, user_token="tok", request=work_on(number=None))
    assert isinstance(no_number, Err)
    assert await start_work(FakeRunner(), forge, config, user_token="tok", request=work_on(text="  ")) == Err(
        Invalid("the request is empty")
    )
