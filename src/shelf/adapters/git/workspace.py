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


@dataclass(frozen=True, slots=True)
class GitWorkspace:
    """One clone, alive for one step."""

    path: Path
    branch: str
    pushes: bool
    auth: tuple[str, ...] = ()
    secrets: tuple[str, ...] = ()

    async def run(self, command: str) -> CheckResult:
        """Run a shell command in the clone."""
        # The commands are the repository's own checks, from its reviewed .shelf/config.toml: a shell is the point.
        return await _exec([command], self.path, shell=True)  # noqa: S604

    async def commit_and_push(self, message: str) -> bool:
        """Commit what changed and push the branch; ``False`` when nothing changed."""
        if not self.pushes:
            return False
        await _git(self.path, "add", "--all")
        if (await _git(self.path, "status", "--porcelain")).output.strip() == "":
            return False
        await _git(self.path, "-c", "commit.gpgsign=false", "commit", "-m", message)
        await _git(self.path, "push", "origin", f"HEAD:refs/heads/{self.branch}", auth=self.auth, secrets=self.secrets)
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
            await _git(
                directory,
                "clone",
                "--quiet",
                "--branch",
                checkout.base,
                url,
                str(directory / "repo"),
                auth=auth,
                secrets=secrets,
            )
            repo = directory / "repo"
            await _git(repo, "config", "user.name", BOT_NAME)
            await _git(repo, "config", "user.email", BOT_EMAIL)
            if checkout.pull_request is not None:
                await _git(
                    repo, "fetch", "--quiet", "origin", f"pull/{checkout.pull_request}/head", auth=auth, secrets=secrets
                )
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
            yield GitWorkspace(repo, checkout.branch, pushes=True, auth=auth, secrets=secrets)
        finally:
            shutil.rmtree(directory, ignore_errors=True)
