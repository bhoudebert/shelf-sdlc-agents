"""``Workspaces`` over the git command line: a temporary clone per step, removed when the step ends."""

import asyncio
import base64
import shutil
import tempfile
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from shelf.ports.workspace import Checkout, CheckResult

BOT_NAME = "shelf-sdlc[bot]"
BOT_EMAIL = "shelf-sdlc[bot]@users.noreply.github.com"


def github_remote(checkout: Checkout) -> str:
    """The HTTPS URL of the repository on GitHub. It carries no credential: anything in the clone can be read."""
    return f"https://github.com/{checkout.repo.full_name}.git"


def github_auth(checkout: Checkout) -> tuple[str, ...]:
    """The git options that authenticate one command as the App, without writing the token into the clone.

    The token travels in an HTTP header for that command only, so it is never in ``.git/config``, where an agent could
    read it.
    """
    credentials = base64.b64encode(f"x-access-token:{checkout.token}".encode()).decode()
    return ("-c", f"http.https://github.com/.extraheader=AUTHORIZATION: basic {credentials}")


def secrets_of(checkout: Checkout) -> tuple[str, ...]:
    """Every form of the token that must never appear in an error message."""
    return (checkout.token, base64.b64encode(f"x-access-token:{checkout.token}".encode()).decode())


async def _exec(args: list[str], cwd: Path | None, *, shell: bool = False) -> CheckResult:
    command = args[0] if shell else " ".join(args)
    if shell:
        process = await asyncio.create_subprocess_shell(
            command, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    output, _ = await process.communicate()
    return CheckResult(command, process.returncode or 0, output.decode(errors="replace"))


WORKFLOWS_HINT = (
    "GitHub refuses a push that changes .github/workflows unless the App has the Workflows permission, which is not "
    "granted by default because a changed workflow runs with the repository's secrets. To allow it: the App's "
    "settings, Permissions & events, Repository permissions, Workflows: Read and write, then accept the change on "
    "each installation. Otherwise make that change by hand, or ask the agents not to touch the workflow files."
)


def explain_push_failure(message: str) -> str:
    """The push error, with what to do about it when it is the missing Workflows permission."""
    if "workflows" in message and "permission" in message:
        return f"{message}\n\n{WORKFLOWS_HINT}"
    return message


async def _git(
    directory: Path, *args: str, check: bool = True, auth: tuple[str, ...] = (), secrets: tuple[str, ...] = ()
) -> CheckResult:
    result = await _exec(["git", *auth, *args], directory)
    if check and result.exit_code != 0:
        message = f"git {args[0]} failed (exit {result.exit_code}): {result.output.strip()}"
        for secret in filter(None, secrets):
            message = message.replace(secret, "***")
        raise RuntimeError(message)
    return result


INITIAL_COMMIT = "chore: initialise the repository"


async def _clone_without_base(  # noqa: PLR0913, PLR0917 - one clone's worth of context
    directory: Path,
    repo: Path,
    url: str,
    checkout: Checkout,
    auth: tuple[str, ...],
    secrets: tuple[str, ...],
    failure: RuntimeError,
) -> None:
    """The clone of the base branch failed: say why, or, for a repository with nothing in it, start its base branch.

    A repository that was just created has no commit and so no branch at all, and a pull request needs a base to open
    against. The one thing done for it is an empty first commit on the base branch; a repository that has other
    branches but not this one, or that cannot be reached, is reported as it is.
    """
    listing = await _git(directory, "ls-remote", "--heads", url, check=False, auth=auth)
    if listing.exit_code != 0:
        raise failure
    branches = [line.split("refs/heads/", 1)[1] for line in listing.output.splitlines() if "refs/heads/" in line]
    if branches:
        message = (
            f"{checkout.repo.full_name} has no branch '{checkout.base}' to start from (it has: "
            f"{', '.join(sorted(branches)[:10])}). Name the right one with base_branch in .shelf/config.toml."
        )
        raise RuntimeError(message) from failure
    if checkout.pull_request is not None:
        message = f"{checkout.repo.full_name} is empty, so it has no pull request #{checkout.pull_request}."
        raise RuntimeError(message) from failure
    shutil.rmtree(repo, ignore_errors=True)
    await _git(directory, "clone", "--quiet", url, str(repo), auth=auth, secrets=secrets)
    await _git(repo, "config", "user.name", BOT_NAME)
    await _git(repo, "config", "user.email", BOT_EMAIL)
    await _git(repo, "checkout", "--quiet", "-b", checkout.base)
    await _git(repo, "-c", "commit.gpgsign=false", "commit", "--quiet", "--allow-empty", "-m", INITIAL_COMMIT)
    await _git(repo, "push", "--quiet", "origin", f"HEAD:refs/heads/{checkout.base}", auth=auth, secrets=secrets)


@dataclass(frozen=True, slots=True)
class GitWorkspace:
    """One clone, alive for one step."""

    path: Path
    branch: str
    pushes: bool
    auth: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()
    lease: str = ""
    """The commit the branch was at when it was cloned, for a branch that belongs to someone's pull request."""

    async def run(self, command: str) -> CheckResult:
        """Run a shell command in the clone."""
        # The commands are the repository's own checks, from its reviewed .shelf/config.toml: a shell is the point.
        return await _exec([command], self.path, shell=True)  # noqa: S604

    async def commit_and_push(self, message: str) -> bool:
        """Commit what changed and push the branch; ``False`` when nothing changed.

        On a branch that belongs to a pull request (``lease`` set) a rebase that changed the history counts as a change
        although nothing is left to commit, and the push replaces the branch only if it is still where it was cloned.
        """
        if not self.pushes:
            return False
        await _git(self.path, "add", "--all")
        dirty = (await _git(self.path, "status", "--porcelain")).output.strip() != ""
        if dirty:
            await _git(self.path, "-c", "commit.gpgsign=false", "commit", "-m", message)
        elif not self.lease or (await _git(self.path, "rev-parse", "HEAD")).output.strip() == self.lease:
            return False
        target = f"refs/heads/{self.branch}"
        guard = (f"--force-with-lease={target}:{self.lease}",) if self.lease else ()
        try:
            await _git(self.path, "push", *guard, "origin", f"HEAD:{target}", auth=self.auth, secrets=self.secrets)
        except RuntimeError as error:
            raise RuntimeError(explain_push_failure(str(error))) from error
        return True


@dataclass(frozen=True, slots=True)
class GitWorkspaces:
    """Clones from ``remote`` (GitHub by default; a local path in tests)."""

    remote: Callable[[Checkout], str] = github_remote
    authenticate: Callable[[Checkout], tuple[str, ...]] = github_auth
    root: Path | None = None

    @asynccontextmanager
    async def open(self, checkout: Checkout) -> AsyncGenerator[GitWorkspace]:
        """Clone fresh: the pull request head for a review, otherwise the work's branch (cut from base if new)."""
        directory = Path(tempfile.mkdtemp(prefix="shelf-", dir=self.root))
        try:
            url = self.remote(checkout)
            auth, secrets = self.authenticate(checkout), secrets_of(checkout)
            repo = directory / "repo"
            try:
                await _git(
                    directory, "clone", "--quiet", "--branch", checkout.base, url, str(repo), auth=auth, secrets=secrets
                )
            except RuntimeError as error:
                await _clone_without_base(directory, repo, url, checkout, auth, secrets, error)
            await _git(repo, "config", "user.name", BOT_NAME)
            await _git(repo, "config", "user.email", BOT_EMAIL)
            if checkout.pull_request is not None:
                try:
                    await _git(
                        repo,
                        "fetch",
                        "--quiet",
                        "origin",
                        f"pull/{checkout.pull_request}/head",
                        auth=auth,
                        secrets=secrets,
                    )
                except RuntimeError as error:
                    message = (
                        f"Pull request #{checkout.pull_request} could not be fetched from {checkout.repo.full_name}: "
                        f"that repository has no such pull request, or the App cannot see it. Check that the work "
                        f"was started on the right repository. ({error})"
                    )
                    raise RuntimeError(message) from error
                await _git(repo, "checkout", "--quiet", "--detach", "FETCH_HEAD")
                yield GitWorkspace(repo, checkout.branch, pushes=False)
                return
            existing = await _git(
                repo, "ls-remote", "--exit-code", "--heads", "origin", checkout.branch, check=False, auth=auth
            )
            if existing.exit_code == 0:
                await _git(repo, "fetch", "--quiet", "origin", checkout.branch, auth=auth, secrets=secrets)
                await _git(repo, "checkout", "--quiet", "-B", checkout.branch, "FETCH_HEAD")
            else:
                await _git(repo, "checkout", "--quiet", "-b", checkout.branch)
            yield GitWorkspace(repo, checkout.branch, pushes=True, auth=auth, secrets=secrets, lease=checkout.lease)
        finally:
            shutil.rmtree(directory, ignore_errors=True)
