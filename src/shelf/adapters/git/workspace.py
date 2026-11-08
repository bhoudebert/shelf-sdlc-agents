"""``Workspaces`` over the git command line: a temporary clone per step, removed when the step ends."""

import asyncio
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
    """The HTTPS URL of the repository on GitHub, authenticated as the App."""
    return f"https://x-access-token:{checkout.token}@github.com/{checkout.repo.full_name}.git"


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


async def _git(directory: Path, *args: str, check: bool = True, secret: str = "") -> CheckResult:
    result = await _exec(["git", *args], directory)
    if check and result.exit_code != 0:
        message = f"git {args[0]} failed (exit {result.exit_code}): {result.output.strip()}"
        raise RuntimeError(message.replace(secret, "***") if secret else message)
    return result


@dataclass(frozen=True, slots=True)
class GitWorkspace:
    """One clone, alive for one step."""

    path: Path
    branch: str
    pushes: bool

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
        await _git(self.path, "push", "origin", f"HEAD:refs/heads/{self.branch}")
        return True


@dataclass(frozen=True, slots=True)
class GitWorkspaces:
    """Clones from ``remote`` (GitHub by default; a local path in tests)."""

    remote: Callable[[Checkout], str] = github_remote
    root: Path | None = None

    @asynccontextmanager
    async def open(self, checkout: Checkout) -> AsyncGenerator[GitWorkspace]:
        """Clone fresh: the pull request head for a review, otherwise the work's branch (cut from base if new)."""
        directory = Path(tempfile.mkdtemp(prefix="shelf-", dir=self.root))
        try:
            url = self.remote(checkout)
            await _git(
                directory,
                "clone",
                "--quiet",
                "--branch",
                checkout.base,
                url,
                str(directory / "repo"),
                secret=checkout.token,
            )
            repo = directory / "repo"
            await _git(repo, "config", "user.name", BOT_NAME)
            await _git(repo, "config", "user.email", BOT_EMAIL)
            if checkout.pull_request is not None:
                await _git(repo, "fetch", "--quiet", "origin", f"pull/{checkout.pull_request}/head")
                await _git(repo, "checkout", "--quiet", "--detach", "FETCH_HEAD")
                yield GitWorkspace(repo, checkout.branch, pushes=False)
                return
            existing = await _git(repo, "ls-remote", "--exit-code", "--heads", "origin", checkout.branch, check=False)
            if existing.exit_code == 0:
                await _git(repo, "fetch", "--quiet", "origin", checkout.branch)
                await _git(repo, "checkout", "--quiet", "-B", checkout.branch, "FETCH_HEAD")
            else:
                await _git(repo, "checkout", "--quiet", "-b", checkout.branch)
            yield GitWorkspace(repo, checkout.branch, pushes=True)
        finally:
            shutil.rmtree(directory, ignore_errors=True)
