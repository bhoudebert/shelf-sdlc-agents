import subprocess
from pathlib import Path

import pytest

from shelf.adapters.git.workspace import GitWorkspaces
from shelf.domain.model import RepoRef
from shelf.ports.workspace import Checkout

REPO = RepoRef("acme", "shop")


def git(directory: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=directory, check=True, capture_output=True, text=True)  # noqa: S603, S607
    return done.stdout.strip()


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    bare = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    git(tmp_path, "init", "--quiet", "--initial-branch=main", str(seed))
    git(seed, "config", "user.name", "seed")
    git(seed, "config", "user.email", "seed@example.org")
    (seed / "README.md").write_text("shop\n")
    git(seed, "add", "--all")
    git(seed, "commit", "--quiet", "-m", "chore: seed")
    git(seed, "remote", "add", "origin", str(bare))
    git(seed, "push", "--quiet", "origin", "main")
    return bare


def workspaces(origin: Path, tmp_path: Path) -> GitWorkspaces:
    return GitWorkspaces(remote=lambda checkout: str(origin), root=tmp_path)


def checkout(**changes: object) -> Checkout:
    base = {"repo": REPO, "token": "tok", "branch": "shelf/work-1", "base": "main", "pull_request": None}
    return Checkout(**{**base, **changes})  # type: ignore[arg-type]


async def test_a_step_commits_and_pushes_a_new_branch_cut_from_base(origin: Path, tmp_path: Path) -> None:
    async with workspaces(origin, tmp_path).open(checkout()) as workspace:
        (workspace.path / "docs").mkdir()
        (workspace.path / "docs" / "spec.md").write_text("spec\n")
        assert await workspace.commit_and_push("chore(shelf): intake")
    assert git(origin, "log", "--format=%s", "shelf/work-1").splitlines()[0] == "chore(shelf): intake"
    assert git(origin, "log", "--format=%an", "-1", "shelf/work-1") == "shelf-sdlc[bot]"


async def test_nothing_is_pushed_when_nothing_changed(origin: Path, tmp_path: Path) -> None:
    async with workspaces(origin, tmp_path).open(checkout()) as workspace:
        assert not await workspace.commit_and_push("chore: nothing")
    assert "shelf/work-1" not in git(origin, "branch", "--list")


async def test_a_later_step_continues_the_branch_a_previous_step_pushed(origin: Path, tmp_path: Path) -> None:
    async with workspaces(origin, tmp_path).open(checkout()) as first:
        (first.path / "a.txt").write_text("a\n")
        await first.commit_and_push("chore: a")
    async with workspaces(origin, tmp_path).open(checkout()) as second:
        assert (second.path / "a.txt").exists()
        (second.path / "b.txt").write_text("b\n")
        await second.commit_and_push("chore: b")
    assert git(origin, "log", "--format=%s", "shelf/work-1").splitlines()[:2] == ["chore: b", "chore: a"]


async def test_the_clone_is_removed_when_the_step_ends(origin: Path, tmp_path: Path) -> None:
    async with workspaces(origin, tmp_path).open(checkout()) as workspace:
        clone = workspace.path
        assert clone.exists()
    assert not clone.exists()


async def test_checks_run_in_the_clone_and_report_their_exit_code(origin: Path, tmp_path: Path) -> None:
    async with workspaces(origin, tmp_path).open(checkout()) as workspace:
        ok = await workspace.run("test -f README.md && echo found")
        bad = await workspace.run("echo nope >&2; exit 3")
    assert (ok.exit_code, ok.output.strip()) == (0, "found")
    assert (bad.exit_code, bad.output.strip()) == (3, "nope")


async def test_a_failed_clone_never_leaks_the_token(origin: Path, tmp_path: Path) -> None:
    broken = GitWorkspaces(remote=lambda c: f"https://x-access-token:{c.token}@127.0.0.1:9/none.git", root=tmp_path)
    with pytest.raises(RuntimeError) as error:
        async with broken.open(checkout(token="s3cret")):
            pass
    assert "s3cret" not in str(error.value)
