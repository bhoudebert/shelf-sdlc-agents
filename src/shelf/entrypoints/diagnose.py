"""``shelf-diagnose``: replays what a step does to reach a repository and a pull request, and says where it breaks.

Run it where the worker runs, with a work id or a pull request::

    docker compose -f deploy/compose.yml exec worker shelf-diagnose work-c115df6263fc
    docker compose -f deploy/compose.yml exec worker shelf-diagnose bhoudebert/nixos-config#2

It uses the App's real credentials (never printed), so the answer is what a step would meet: which installation covers
the repository and what it was granted, what GitHub says the pull request is, what git can list and fetch from it, and,
for a work id, what each failed attempt of its workflow said. The output is safe to paste into an issue or a chat.
"""

import asyncio
import json
import os
import re
import sys
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from shelf.adapters.git.workspace import GitWorkspaces, _git, github_auth, secrets_of  # pyright: ignore[reportPrivateUsage]
from shelf.adapters.github_app.app_auth import app_jwt, installation_token
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.entrypoints import settings as settings_module
from shelf.entrypoints.wiring import app_settings, connect
from shelf.ports.workspace import Checkout

OK = "✓"
BAD = "✗"
NOTE = "·"
TARGET = re.compile(r"^(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)(?:#(?P<number>\d+))?$")
FAILURES = 6
"""How many of a work's latest failed attempts are shown."""

type GitProbe = Callable[[RepoRef, str, int | None], Awaitable[Sequence[str]]]
"""Lists the refs git can see, and tries the checkout of a pull request the way a review does."""


@dataclass(frozen=True, slots=True)
class Line:
    """One finding: ``OK``, ``BAD`` or ``NOTE``, and what it says."""

    mark: str
    text: str


def render(lines: Sequence[Line], secrets: Sequence[str] = ()) -> str:
    """The report as text, with every secret blanked."""
    text = "\n".join(f"{line.mark} {line.text}" for line in lines)
    for secret in filter(None, secrets):
        text = text.replace(secret, "***")
    return text


def parse_target(target: str) -> tuple[RepoRef, int | None] | None:
    """``owner/name`` or ``owner/name#7``; ``None`` for anything else (a work id, for instance)."""
    found = TARGET.match(target)
    if found is None:
        return None
    number = found.group("number")
    return RepoRef(found.group("owner"), found.group("name")), int(number) if number else None


async def diagnose_repository(  # noqa: PLR0913, PLR0917 - one knob per dependency, injected so tests need no network
    client: httpx.AsyncClient,
    settings: GitHubAppSettings,
    repo: RepoRef,
    number: int | None,
    probe: GitProbe,
    now: datetime,
) -> list[Line]:
    """Follow the path of a step: the App, its installation, the token, the repository, the pull request, git."""
    lines: list[Line] = []
    app_headers = _headers(app_jwt(settings, now))
    try:
        app = await _json(client, f"{settings.api_url}/app", app_headers)
    except httpx.HTTPError as error:
        return [Line(BAD, f"cannot act as the App ({_why(error)}): the App id or private key is wrong")]
    permissions = ", ".join(f"{name}:{level}" for name, level in sorted(app.get("permissions", {}).items()))
    lines.append(Line(OK, f"the App is {app.get('slug')} (id {app.get('id')}); it asks for {permissions}"))
    lines.append(Line(NOTE, "subscribed events: " + (", ".join(sorted(app.get("events", []))) or "none")))
    try:
        installation = await _json(client, f"{settings.api_url}/repos/{repo.full_name}/installation", app_headers)
    except httpx.HTTPError as error:
        lines.append(Line(BAD, f"the App is not installed on {repo.full_name} ({_why(error)}): install it there"))
        return lines
    granted = ", ".join(f"{name}:{level}" for name, level in sorted(installation.get("permissions", {}).items()))
    lines.append(
        Line(
            OK,
            f"installation {installation['id']} covers {repo.full_name} "
            f"({installation.get('repository_selection')} repositories, on {installation['account']['login']}); "
            f"granted {granted}",
        )
    )
    if installation.get("suspended_at"):
        lines.append(Line(BAD, f"the installation is suspended since {installation['suspended_at']}"))
    lines += _permission_gaps(app.get("permissions", {}), installation.get("permissions", {}))
    try:
        token = (await installation_token(client, settings, int(installation["id"]), now)).value
    except httpx.HTTPError as error:
        lines.append(Line(BAD, f"cannot mint an installation token ({_why(error)})"))
        return lines
    lines.append(Line(OK, "an installation token was minted"))
    headers = _headers(token)
    lines += await _repository(client, settings, repo, headers)
    head_ref = ""
    if number is not None:
        found, head_ref = await _pull_request(client, settings, repo, number, headers)
        lines += found
    lines += [Line(NOTE, f"git: {text}") for text in await probe(repo, token, number)]
    if head_ref:
        lines.append(Line(NOTE, f"the pull request's branch is {head_ref}"))
    return lines


def _permission_gaps(asked: dict[str, str], granted: dict[str, str]) -> list[Line]:
    """Permissions the App asks for that this installation has not accepted yet."""
    levels = {"read": 1, "write": 2, "admin": 3}
    gaps = [
        f"{name} (asked {level}, granted {granted.get(name, 'none')})"
        for name, level in sorted(asked.items())
        if levels.get(granted.get(name, ""), 0) < levels.get(level, 0)
    ]
    if not gaps:
        return []
    return [Line(BAD, "this installation has not accepted: " + ", ".join(gaps) + ". Accept them on the installation.")]


async def _repository(
    client: httpx.AsyncClient, settings: GitHubAppSettings, repo: RepoRef, headers: dict[str, str]
) -> list[Line]:
    try:
        data = await _json(client, f"{settings.api_url}/repos/{repo.full_name}", headers)
    except httpx.HTTPError as error:
        return [Line(BAD, f"the token cannot read {repo.full_name} ({_why(error)})")]
    flags = [name for name in ("private", "fork", "archived") if data.get(name)]
    return [
        Line(
            OK,
            f"{repo.full_name}: default branch {data.get('default_branch')}"
            + (f" ({', '.join(flags)})" if flags else ""),
        )
    ]


async def _pull_request(
    client: httpx.AsyncClient, settings: GitHubAppSettings, repo: RepoRef, number: int, headers: dict[str, str]
) -> tuple[list[Line], str]:
    try:
        pull = await _json(client, f"{settings.api_url}/repos/{repo.full_name}/pulls/{number}", headers)
    except httpx.HTTPError as error:
        return [Line(BAD, f"pull request #{number} cannot be read in {repo.full_name} ({_why(error)})")], ""
    head: dict[str, Any] = pull.get("head", {})
    head_data: dict[str, Any] = head.get("repo") or {}
    head_repo: str | None = head_data.get("full_name")
    state = "merged" if pull.get("merged") else pull.get("state")
    text = (
        f"pull request #{number}: {state}{', draft' if pull.get('draft') else ''}, "
        f"{head.get('ref')} ({str(head.get('sha'))[:8]}) into {pull.get('base', {}).get('ref')}"
    )
    lines = [Line(OK, text)]
    if head_repo != repo.full_name:
        lines.append(
            Line(BAD if head_repo is None else NOTE, f"its head is on {head_repo or 'a deleted fork'}, not here")
        )
    return lines, str(head.get("ref") or "")


async def diagnose_work(temporal: Any, work_id: str) -> tuple[list[Line], RepoRef | None, int | None]:  # noqa: ANN401
    """What the workflow of ``work_id`` is and what each failed attempt said, with the repository it works on."""
    handle = temporal.get_workflow_handle(work_id)
    try:
        description = await handle.describe()
    except Exception as error:  # noqa: BLE001 - say why instead of a traceback
        return (
            [Line(BAD, f"{work_id}: Temporal cannot find it ({type(error).__name__}: {str(error)[:200]})")],
            None,
            None,
        )
    memo = await description.memo()
    repo = RepoRef.parse(str(memo["repo"])) if "repo" in memo else None
    number = int(memo["pull_request"]) if memo.get("pull_request") is not None else None
    lines = [
        Line(OK, f"{work_id}: {description.status.name if description.status else 'unknown'}"),
        Line(
            NOTE,
            f"repository {memo.get('repo')}, entry {memo.get('entry')}, requester {memo.get('requester')}, "
            f"pull request {memo.get('pull_request') or 'none'}",
        ),
    ]
    lines += _failures(await handle.fetch_history())
    return lines, repo, number


def _failures(history: Any) -> list[Line]:  # noqa: ANN401
    """The last failed or timed-out attempts in a workflow's history, with when and what."""
    found: list[Line] = []
    for event in history.events:
        when = event.event_time.ToDatetime().replace(tzinfo=UTC).strftime("%d %b %H:%M:%S UTC")
        if event.HasField("activity_task_failed_event_attributes"):
            failure = event.activity_task_failed_event_attributes.failure
            found.append(Line(BAD, f"{when} an attempt failed: {_deepest(failure)}"))
        elif event.HasField("activity_task_timed_out_event_attributes"):
            failure = event.activity_task_timed_out_event_attributes.failure
            found.append(Line(BAD, f"{when} an attempt timed out: {_deepest(failure)}"))
        elif event.HasField("workflow_task_failed_event_attributes"):
            failure = event.workflow_task_failed_event_attributes.failure
            found.append(Line(BAD, f"{when} the workflow itself failed: {_deepest(failure)}"))
    if not found:
        return [Line(NOTE, "no failed attempt in its history")]
    return [Line(NOTE, f"{len(found)} failed attempt(s); the latest {min(len(found), FAILURES)}:"), *found[-FAILURES:]]


def _deepest(failure: Any) -> str:  # noqa: ANN401
    """The message of the innermost cause of a Temporal failure, which is the one that says what really happened."""
    while failure.HasField("cause"):
        failure = failure.cause
    return " ".join(str(failure.message).split())[:600]


async def git_probe(repo: RepoRef, token: str, number: int | None) -> list[str]:
    """What git lists from the remote with the token, and whether the checkout a review does works."""
    checkout = Checkout(repo, token, "diagnose", "main", number)
    auth, secrets = github_auth(checkout), secrets_of(checkout)
    url = f"https://github.com/{repo.full_name}.git"
    out: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shelf-diagnose-") as directory:
        patterns = ["refs/heads/main"] + ([f"refs/pull/{number}/*"] if number is not None else [])
        listed = await _git(Path(directory), "ls-remote", url, *patterns, check=False, auth=auth, secrets=secrets)
        out.append(f"ls-remote {' '.join(patterns)} -> exit {listed.exit_code}")
        out += [f"  {line.split()[0][:8]} {line.split()[1]}" for line in listed.output.splitlines() if line.strip()]
        if listed.exit_code == 0 and not listed.output.strip():
            out.append("  (nothing listed: the remote shows none of those refs to this token)")
    try:
        async with GitWorkspaces().open(checkout) as workspace:
            head = await _git(workspace.path, "rev-parse", "--short", "HEAD", check=False)
            out.append(f"the checkout a review does works, at {head.output.strip()}")
    except RuntimeError as error:
        out.append(f"the checkout a review does FAILS: {error}")
    return out


def guard_findings(doctor: str | None, report: str | None) -> list[Line]:
    """What ``warden doctor`` and ``warden report --json`` said, as findings; ``None`` means the guard is not installed.

    A warning counts as a failure: an agent that runs unguarded is what this system must not do.
    """
    if doctor is None:
        return [Line(NOTE, "the guard (warden) is not installed here")]
    marks = {"ok": OK, "warn": BAD, "fail": BAD, "error": BAD}
    lines: list[Line] = []
    for raw in doctor.splitlines():
        status, _, text = raw.strip().partition(" ")
        if status in marks and text.strip():
            lines.append(Line(marks[status], f"guard: {text.strip()}"))
    try:
        counts = json.loads(report or "")
        lines.append(
            Line(
                NOTE,
                f"guard: {counts['calls']} calls recorded, {counts['would_stop']} stopped or would be stopped",
            )
        )
    except (ValueError, KeyError, TypeError):
        lines.append(Line(NOTE, "guard: its report could not be read"))
    return lines


async def _warden(*args: str) -> str | None:
    """What a ``warden`` command printed, or ``None`` when there is no such program."""
    try:
        process = await asyncio.create_subprocess_exec(
            "warden", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
        )
        out, _ = await asyncio.wait_for(process.communicate(), 20)
    except FileNotFoundError:
        return None
    except (TimeoutError, OSError):
        return ""
    return out.decode()


def _headers(bearer: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _json(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> Any:  # noqa: ANN401 - GitHub's JSON
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _why(error: httpx.HTTPError) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"GitHub answered {error.response.status_code}"
    return type(error).__name__


async def run(target: str) -> int:
    """Diagnose ``target`` (a work id or a pull request) and print the report; the exit code says if all is well."""
    settings = settings_module.from_environ(
        {"PUBLIC_URL": "http://diagnose", "SESSION_SECRET": "diagnose", **os.environ}
    )
    if settings.github is None:
        print(f"{BAD} no GitHub App is configured in this environment")  # noqa: T201
        return 1
    github = app_settings(settings.github)
    lines: list[Line] = [Line(NOTE, f"shelf {settings.revision}, {datetime.now(UTC):%d %b %H:%M UTC}")]
    parsed = parse_target(target)
    repo, number = parsed or (None, None)
    if parsed is None:
        temporal = await connect(settings)
        found, repo, number = await diagnose_work(temporal, target)
        lines += found
    if repo is not None:
        async with httpx.AsyncClient(timeout=30) as client:
            lines += await diagnose_repository(client, github, repo, number, git_probe, datetime.now(UTC))
    lines += guard_findings(await _warden("doctor"), await _warden("report", "--json"))
    print(render(lines))  # noqa: T201
    return 0 if all(line.mark != BAD for line in lines) else 1


def main() -> None:
    """Console entry point: ``shelf-diagnose <work-id | owner/repo#number>``."""
    if len(sys.argv) != 2:  # noqa: PLR2004
        print(__doc__)  # noqa: T201
        sys.exit(2)
    sys.exit(asyncio.run(run(sys.argv[1])))


if __name__ == "__main__":
    main()
