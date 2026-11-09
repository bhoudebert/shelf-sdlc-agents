"""Starting work, deciding for it, and the board: the use cases behind the UI."""

from collections.abc import Sequence

from shelf.application.errors import Invalid, NotAllowed, NotFound, Refusal
from shelf.domain.access import AccessRules, is_admin
from shelf.domain.config import may_decide
from shelf.domain.model import WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint
from shelf.domain.result import Err, Ok, Result
from shelf.domain.work import DecisionKind, PersonDecided
from shelf.ports.configs import RepoConfigs
from shelf.ports.forge import Forge
from shelf.ports.runner import WorkRunner


async def start_work(
    runner: WorkRunner,
    forge: Forge,
    configs: RepoConfigs,
    *,
    user_token: str,
    request: WorkRequest,
) -> Result[WorkId, Refusal]:
    """Start work on a repository the person can see, at an entry point the repository enables."""
    visible = await forge.repositories(user_token)
    if request.repo not in visible:
        return Err(NotFound(request.repo.full_name))
    config = await configs.load(request.repo)
    if request.entry not in config.entries:
        return Err(Invalid(f"{request.entry} is not enabled on {request.repo.full_name}"))
    if request.entry is EntryPoint.PULL_REQUEST_REVIEW:
        if request.pull_request is None:
            return Err(Invalid("a pull request number is required to review a pull request"))
        if not await forge.pull_request_exists(user_token, request.repo, request.pull_request):
            return Err(
                Invalid(f"{request.repo.full_name} has no pull request #{request.pull_request}: check the repository")
            )
    if request.entry is not EntryPoint.PULL_REQUEST_REVIEW and not request.text.strip():
        return Err(Invalid("the request is empty"))
    return Ok(await runner.start(request))


async def decide_work(  # noqa: PLR0913
    runner: WorkRunner,
    configs: RepoConfigs,
    rules: AccessRules,
    *,
    work_id: WorkId,
    login: str,
    kind: DecisionKind,
    note: str = "",
) -> Result[None, Refusal]:
    """Deliver ``login``'s decision to the work, if their role in the repository allows it at this phase."""
    view = await runner.view(work_id)
    if view is None:
        return Err(NotFound(work_id))
    config = await configs.load(view.repo)
    if not may_decide(config, login, view.phase, admin=is_admin(rules, login)):
        return Err(NotAllowed(f"{login} may not decide at {view.phase} on {view.repo.full_name}"))
    await runner.decide(work_id, PersonDecided(login, kind, note))
    return Ok(None)


async def board(runner: WorkRunner, forge: Forge, *, user_token: str, everything: bool = False) -> Sequence[WorkView]:
    """The work of every repository the person can see, or of every repository when ``everything`` (administrators)."""
    if everything:
        return await runner.list(None)
    return await runner.list(await forge.repositories(user_token))
