import os
import subprocess
from pathlib import Path

import pytest

from shelf.adapters.git.workspace import WORKFLOWS_HINT, GitWorkspaces, explain_push_failure
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


def test_the_remote_url_carries_no_credential_so_nothing_in_the_clone_can_leak_it() -> None:
    from shelf.adapters.git.workspace import github_auth, github_remote, secrets_of  # noqa: PLC0415

    target = checkout(token="s3cret")
    assert github_remote(target) == "https://github.com/acme/shop.git"
    assert "s3cret" not in github_remote(target)
    header = " ".join(github_auth(target))
    assert "extraheader" in header
    assert "s3cret" not in header  # it travels base64-encoded, for that one command only
    assert "s3cret" in secrets_of(target)
    assert any(secret != "s3cret" for secret in secrets_of(target))


async def test_a_clone_made_by_the_workspace_has_no_token_anywhere_in_its_git_config(
    origin: Path, tmp_path: Path
) -> None:
    async with workspaces(origin, tmp_path).open(checkout(token="s3cret")) as workspace:
        config = (workspace.path / ".git" / "config").read_text()
    assert "s3cret" not in config


def test_a_push_refused_for_the_workflows_permission_says_how_to_allow_it() -> None:
    refused = (
        "git push failed (exit 1): ! [remote rejected] HEAD -> shelf/work-1 (refusing to allow a GitHub App to create "
        "or update workflow `.github/workflows/nix.yml` without `workflows` permission)"
    )
    explained = explain_push_failure(refused)
    assert explained.startswith(refused)
    assert explained.endswith(WORKFLOWS_HINT)
    assert "Workflows: Read and write" in explained


def test_any_other_push_failure_is_left_as_it_is() -> None:
    assert (
        explain_push_failure("git push failed (exit 1): non-fast-forward")
        == "git push failed (exit 1): non-fast-forward"
    )


async def test_a_pull_request_the_repository_does_not_have_is_named_in_the_error(origin: Path, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError) as raised:
        async with workspaces(origin, tmp_path).open(checkout(pull_request=2)):
            pass
    message = str(raised.value)
    assert "Pull request #2 could not be fetched from acme/shop" in message
    assert "started on the right repository" in message
    assert "tok" not in message.replace("token", "")  # the token never appears


def own_branch(origin: Path, tmp_path: Path) -> str:
    """A branch an author pushed for a pull request; returns the commit it is at."""
    author = tmp_path / "author"
    git(tmp_path, "clone", "--quiet", str(origin), str(author))
    git(author, "config", "user.name", "author")
    git(author, "config", "user.email", "author@example.org")
    git(author, "checkout", "--quiet", "-b", "feat/x")
    (author / "x.txt").write_text("x\n")
    git(author, "add", "--all")
    git(author, "commit", "--quiet", "-m", "feat: x")
    git(author, "push", "--quiet", "origin", "feat/x")
    return git(author, "rev-parse", "HEAD")


async def test_a_rebased_branch_that_belongs_to_a_pull_request_is_pushed_although_nothing_is_left_to_commit(
    origin: Path, tmp_path: Path
) -> None:
    tip = own_branch(origin, tmp_path)
    async with workspaces(origin, tmp_path).open(checkout(branch="feat/x", lease=tip)) as workspace:
        assert (workspace.path / "x.txt").exists()
        git(
            workspace.path,
            "-c",
            "user.name=a",
            "-c",
            "user.email=a@b.c",
            "commit",
            "--allow-empty",
            "--amend",
            "-m",
            "feat: x, rebased",
        )
        assert await workspace.commit_and_push("chore: not needed")
    assert git(origin, "log", "--format=%s", "-1", "feat/x") == "feat: x, rebased"


async def test_an_unchanged_branch_that_belongs_to_a_pull_request_is_not_pushed(origin: Path, tmp_path: Path) -> None:
    tip = own_branch(origin, tmp_path)
    async with workspaces(origin, tmp_path).open(checkout(branch="feat/x", lease=tip)) as workspace:
        assert not await workspace.commit_and_push("chore: nothing")
    assert git(origin, "rev-parse", "feat/x") == tip


async def test_the_author_having_pushed_meanwhile_is_never_overwritten(origin: Path, tmp_path: Path) -> None:
    tip = own_branch(origin, tmp_path)
    async with workspaces(origin, tmp_path).open(checkout(branch="feat/x", lease=tip)) as workspace:
        git(
            workspace.path,
            "-c",
            "user.name=a",
            "-c",
            "user.email=a@b.c",
            "commit",
            "--allow-empty",
            "--amend",
            "-m",
            "ours",
        )
        author = tmp_path / "author"
        (author / "y.txt").write_text("y\n")
        git(author, "add", "--all")
        git(author, "commit", "--quiet", "-m", "feat: y")
        git(author, "push", "--quiet", "origin", "feat/x")  # the author pushes while the work is going on
        with pytest.raises(RuntimeError):
            await workspace.commit_and_push("chore: ours")
    assert git(origin, "log", "--format=%s", "-1", "feat/x") == "feat: y"


@pytest.fixture
def empty_origin(tmp_path: Path) -> Path:
    bare = tmp_path / "empty.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(bare))
    return bare


async def test_an_empty_repository_gets_its_base_branch_and_the_work_goes_on(
    empty_origin: Path, tmp_path: Path
) -> None:
    async with workspaces(empty_origin, tmp_path).open(checkout()) as workspace:
        (workspace.path / "docs").mkdir()
        (workspace.path / "docs" / "spec.md").write_text("spec\n")
        assert await workspace.commit_and_push("chore(shelf): intake")
    assert git(empty_origin, "log", "--format=%s", "main") == "chore: initialise the repository"
    assert git(empty_origin, "log", "--format=%s", "-1", "shelf/work-1") == "chore(shelf): intake"
    assert git(empty_origin, "merge-base", "main", "shelf/work-1") == git(empty_origin, "rev-parse", "main")


async def test_a_repository_without_the_named_base_says_which_branches_it_has(tmp_path: Path) -> None:
    other = tmp_path / "other.git"
    seed = tmp_path / "seed"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=master", str(other))
    git(tmp_path, "init", "--quiet", "--initial-branch=master", str(seed))
    git(seed, "config", "user.name", "seed")
    git(seed, "config", "user.email", "seed@example.org")
    git(seed, "commit", "--quiet", "--allow-empty", "-m", "seed")
    git(seed, "remote", "add", "origin", str(other))
    git(seed, "push", "--quiet", "origin", "master")
    with pytest.raises(RuntimeError, match=r"no branch 'main'.*master.*base_branch"):
        async with workspaces(other, tmp_path).open(checkout()):
            pass
    assert "main" not in git(other, "branch", "--list")


async def test_a_review_of_a_pull_request_on_an_empty_repository_is_refused(empty_origin: Path, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="is empty"):
        async with workspaces(empty_origin, tmp_path).open(checkout(pull_request=3)):
            pass


async def test_a_repository_that_cannot_be_reached_reports_git_s_own_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="git clone failed"):
        async with workspaces(tmp_path / "nowhere.git", tmp_path).open(checkout()):
            pass


async def test_a_check_does_not_see_the_workers_secrets_or_the_model_credential(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "session-secret-value")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", "/run/secrets/github-app.pem")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "model-token-value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "api-key-value")
    async with workspaces(origin, tmp_path).open(checkout()) as workspace:
        printed = await workspace.run("env")
        path = await workspace.run("echo $PATH")
    assert printed.exit_code == 0
    for leaked in ("session-secret-value", "github-app.pem", "model-token-value", "api-key-value"):
        assert leaked not in printed.output
    assert path.output.strip() == os.environ["PATH"]
