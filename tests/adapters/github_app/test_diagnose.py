from datetime import UTC, datetime

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.entrypoints.diagnose import BAD, NOTE, OK, Line, diagnose_repository, parse_target, render

REPO = RepoRef("acme", "shop")
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def test_a_target_is_a_repository_with_or_without_a_pull_request_and_a_work_id_is_neither() -> None:
    assert parse_target("acme/shop#2") == (REPO, 2)
    assert parse_target("acme/shop") == (REPO, None)
    assert parse_target("work-c115df6263fc") is None


def test_every_secret_is_blanked_in_the_report() -> None:
    text = render([Line(OK, "token ghs_secret used"), Line(BAD, "header c2VjcmV0")], ["ghs_secret", "c2VjcmV0"])
    assert "ghs_secret" not in text
    assert "c2VjcmV0" not in text
    assert "***" in text


async def no_git(repo: RepoRef, token: str, number: int | None) -> list[str]:
    return ["ls-remote refs/pull/2/* -> exit 0", "  (nothing listed)"]


def github(settings: GitHubAppSettings, routes: dict[str, tuple[int, dict[str, object]]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(f"{request.method} {request.url.path}", (404, {}))
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def routes(
    *, installed: bool = True, pull: bool = True, accepted: str = "write"
) -> dict[str, tuple[int, dict[str, object]]]:
    found: dict[str, tuple[int, dict[str, object]]] = {
        "GET /app": (
            200,
            {
                "slug": "shelf",
                "id": 1,
                "permissions": {"actions": "read", "contents": "write"},
                "events": ["issue_comment"],
            },
        ),
        "POST /app/installations/9/access_tokens": (201, {"token": "ghs_x", "expires_at": "2026-11-09T13:00:00Z"}),
        "GET /repos/acme/shop": (200, {"default_branch": "main", "private": True}),
    }
    if installed:
        found["GET /repos/acme/shop/installation"] = (
            200,
            {
                "id": 9,
                "repository_selection": "selected",
                "account": {"login": "acme"},
                "permissions": {"actions": "read", "contents": accepted},
            },
        )
    if pull:
        found["GET /repos/acme/shop/pulls/2"] = (
            200,
            {
                "state": "open",
                "head": {"ref": "feat/x", "sha": "abcdef123456", "repo": {"full_name": "acme/shop"}},
                "base": {"ref": "main"},
            },
        )
    return found


async def test_the_path_of_a_step_is_followed_and_reported(settings: GitHubAppSettings) -> None:
    lines = await diagnose_repository(github(settings, routes()), settings, REPO, 2, no_git, NOW)
    text = render(lines)
    assert "installation 9 covers acme/shop (selected repositories, on acme)" in text
    assert "pull request #2: open, feat/x (abcdef12) into main" in text
    assert "git: ls-remote refs/pull/2/* -> exit 0" in text
    assert all(line.mark != BAD for line in lines)


async def test_a_repository_the_app_is_not_installed_on_is_said_plainly(settings: GitHubAppSettings) -> None:
    lines = await diagnose_repository(github(settings, routes(installed=False)), settings, REPO, 2, no_git, NOW)
    assert lines[-1].mark == BAD
    assert "not installed on acme/shop" in lines[-1].text


async def test_a_pull_request_that_does_not_exist_is_said_with_the_status_github_gave(
    settings: GitHubAppSettings,
) -> None:
    lines = await diagnose_repository(github(settings, routes(pull=False)), settings, REPO, 2, no_git, NOW)
    assert any(
        line.mark == BAD and "#2 cannot be read in acme/shop (GitHub answered 404)" in line.text for line in lines
    )


async def test_a_permission_the_installation_has_not_accepted_is_named(settings: GitHubAppSettings) -> None:
    lines = await diagnose_repository(github(settings, routes(accepted="read")), settings, REPO, None, no_git, NOW)
    assert any(line.mark == BAD and "contents (asked write, granted read)" in line.text for line in lines)


def test_notes_are_not_failures() -> None:
    assert Line(NOTE, "x").mark != BAD
