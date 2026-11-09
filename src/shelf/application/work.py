"""Starting work, deciding for it, and the board: the use cases behind the UI."""

from collections.abc import Sequence
from dataclasses import replace

from shelf.application.errors import Invalid, NotAllowed, NotFound, Refusal
from shelf.domain.access import AccessRules, is_admin
from shelf.domain.config import may_decide
from shelf.domain.context_repo import MAX_REPOSITORIES, ContextRepo, mentioned, parse_contexts
from shelf.domain.model import RepoRef, WorkId, WorkRequest, WorkView
from shelf.domain.pipeline import EntryPoint
from shelf.domain.reference import Imported, combine, parse_reference
from shelf.domain.result import Err, Ok, Result
from shelf.domain.work import DecisionKind, PersonDecided
from shelf.ports.configs import RepoConfigs
from shelf.ports.context_sources import ContextSources
from shelf.ports.forge import Forge
from shelf.ports.references import References
from shelf.ports.runner import WorkRunner


async def start_work(  # noqa: PLR0913
    runner: WorkRunner,
    forge: Forge,
    configs: RepoConfigs,
    *,
    user_token: str,
    request: WorkRequest,
    references: References | None = None,
    reference: str = "",
    context_sources: ContextSources | None = None,
    context: str = "",
) -> Result[WorkId, Refusal]:
    """Start work on a repository the person can see, at an entry point the repository enables.

    ``reference`` is optional existing material (an issue, a pull request or a file of the repository): what it says
    becomes the request, followed by what the person typed. ``context`` lists other public repositories to read as
    reference; so are those the request links to.
    """
    visible = await forge.repositories(user_token)
    if request.repo not in visible:
        return Err(NotFound(request.repo.full_name))
    config = await configs.load(request.repo)
    if request.entry not in config.entries:
        return Err(Invalid(f"{request.entry} is not enabled on {request.repo.full_name}"))
    if request.entry in (EntryPoint.PULL_REQUEST_REVIEW, EntryPoint.PULL_REQUEST_WORK):
        refusal = await _pull_request_refusal(forge, user_token, request)
        if refusal is not None:
            return Err(refusal)
    enriched = await _enrich(request, references, reference, context_sources, context)
    if isinstance(enriched, Err):
        return Err(Invalid(enriched.error))
    request = enriched.value
    if request.entry is not EntryPoint.PULL_REQUEST_REVIEW and not request.text.strip():
        return Err(Invalid("the request is empty"))
    return Ok(await runner.start(request))


async def _enrich(
    request: WorkRequest, references: References | None, reference: str, sources: ContextSources | None, context: str
) -> Result[WorkRequest, str]:
    """The request with the other repositories to read and the existing material it starts from, or why not."""
    found = await _context(sources, context, request)
    if isinstance(found, Err):
        return found
    request = replace(request, context=found.value)
    if not reference.strip():
        return Ok(request)
    imported = await _import(references, request.repo, reference)
    if isinstance(imported, Err):
        return imported
    return Ok(replace(request, text=combine(imported.value, request.text)))


async def _context(sources: ContextSources | None, explicit: str, request: WorkRequest) -> Result[tuple[str, ...], str]:
    """The other repositories to read.

    Those the person listed are refused when one cannot be read. Those the request links to are read when public and
    silently left out otherwise, since a link to a private repository is only a mention.
    """
    asked = parse_contexts(explicit)
    if isinstance(asked, Err):
        return asked
    if sources is None:
        return Err("reading other repositories is not available here") if asked.value else Ok(())
    chosen: list[ContextRepo] = []
    for item in asked.value:
        problem = await sources.check(item)
        if problem:
            return Err(problem)
        chosen.append(item)
    for item in mentioned(request.text, request.repo):
        if len(chosen) < MAX_REPOSITORIES and item not in chosen and not await sources.check(item):
            chosen.append(item)
    return Ok(tuple(item.spec for item in chosen))


async def _import(references: References | None, repo: RepoRef, reference: str) -> Result[Imported, str]:
    """Read the reference a person gave, or say why it cannot be used."""
    if references is None:
        return Err("starting from existing material is not available here")
    parsed = parse_reference(reference, repo)
    if isinstance(parsed, Err):
        return parsed
    return await references.read(repo, parsed.value)


async def _pull_request_refusal(forge: Forge, user_token: str, request: WorkRequest) -> Invalid | None:
    """Why the pull request of a request cannot be worked on, or ``None`` when it can."""
    number = request.pull_request
    if number is None:
        return Invalid("a pull request number is required to work on a pull request")
    pull = await forge.pull_request(user_token, request.repo, number)
    if pull is None:
        return Invalid(f"{request.repo.full_name} has no pull request #{number}: check the repository")
    if request.entry is EntryPoint.PULL_REQUEST_WORK and not pull.open:
        return Invalid(f"pull request #{number} is closed")
    if request.entry is EntryPoint.PULL_REQUEST_WORK and not pull.same_repository:
        return Invalid(f"pull request #{number} comes from a fork: the App cannot push to its branch")
    return None


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
