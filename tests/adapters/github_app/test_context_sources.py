import io
import os
import stat
import tarfile
from pathlib import Path

import httpx
import pytest

from shelf.adapters.github_app.context_sources import (
    MAX_FILE,
    GitHubContextSources,
    unpack,
)
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.context_repo import ContextRepo
from shelf.domain.model import RepoRef
from shelf.domain.result import Err, Ok

OLLAMA = ContextRepo(RepoRef("ollama", "ollama"), "v1")


def archive(path: Path, members: list[tuple[str, bytes, int, bytes]]) -> Path:
    """A repository archive: (name, content, mode, type) for each member, under the top folder GitHub adds."""
    with tarfile.open(path, "w:gz") as tar:
        for name, content, mode, kind in members:
            info = tarfile.TarInfo(name)
            info.mode = mode
            info.type = kind
            if kind == tarfile.REGTYPE:
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
            else:
                info.linkname = "/etc/passwd"
                tar.addfile(info)
    return path


REG = tarfile.REGTYPE


def test_only_regular_text_files_are_written_each_read_only_and_never_executable(tmp_path: Path) -> None:
    built = archive(
        tmp_path / "a.tar.gz",
        [
            ("repo-abc/README.md", b"# hi\n", 0o644, REG),
            ("repo-abc/.github/workflows/ci.yml", b"on: push\n", 0o644, REG),
            ("repo-abc/scripts/run.sh", b"#!/bin/sh\nrm -rf /\n", 0o755, REG),
        ],
    )
    result = unpack(built, tmp_path / "out")
    assert result == Ok(3)
    ci = tmp_path / "out" / ".github" / "workflows" / "ci.yml"
    assert ci.read_text() == "on: push\n"
    script = tmp_path / "out" / "scripts" / "run.sh"
    mode = stat.S_IMODE(script.stat().st_mode)
    assert mode & 0o111 == 0, "no execute bit, whatever the repository said"
    assert mode & 0o222 == 0, "read only"


def test_links_devices_and_names_that_leave_the_folder_are_never_written(tmp_path: Path) -> None:
    built = archive(
        tmp_path / "a.tar.gz",
        [
            ("repo-abc/ok.md", b"ok", 0o644, REG),
            ("repo-abc/link", b"", 0o777, tarfile.SYMTYPE),
            ("repo-abc/hard", b"", 0o644, tarfile.LNKTYPE),
            ("repo-abc/dev", b"", 0o644, tarfile.CHRTYPE),
            ("repo-abc/../escape.md", b"no", 0o644, REG),
            ("/absolute.md", b"no", 0o644, REG),
            ("repo-abc/a/../../up.md", b"no", 0o644, REG),
        ],
    )
    assert unpack(built, tmp_path / "out") == Ok(1)
    assert sorted(p.name for p in (tmp_path / "out").rglob("*") if p.is_file()) == ["ok.md"]
    assert not (tmp_path / "escape.md").exists()
    assert not (tmp_path / "up.md").exists()
    assert not (tmp_path / "out" / "link").exists()


def test_binary_oversized_and_too_numerous_files_are_skipped(tmp_path: Path) -> None:
    built = archive(
        tmp_path / "a.tar.gz",
        [
            ("repo-abc/a.md", b"text", 0o644, REG),
            ("repo-abc/logo.png", b"\x89PNG", 0o644, REG),
            ("repo-abc/model.gguf", b"x", 0o644, REG),
            ("repo-abc/blob.dat", b"ab\x00cd", 0o644, REG),
            ("repo-abc/big.md", b"x" * (MAX_FILE + 1), 0o644, REG),
        ],
    )
    assert unpack(built, tmp_path / "out") == Ok(1)


def test_a_folder_can_be_named_so_that_only_it_is_copied(tmp_path: Path) -> None:
    built = archive(
        tmp_path / "a.tar.gz",
        [
            ("repo-abc/docs/ci/a.md", b"a", 0o644, REG),
            ("repo-abc/docs/other.md", b"b", 0o644, REG),
            ("repo-abc/docs2/x.md", b"c", 0o644, REG),
            ("repo-abc/README.md", b"d", 0o644, REG),
        ],
    )
    assert unpack(built, tmp_path / "out", "docs/ci") == Ok(1)
    assert (tmp_path / "out" / "docs" / "ci" / "a.md").exists()


def test_an_archive_with_nothing_readable_says_so(tmp_path: Path) -> None:
    built = archive(tmp_path / "a.tar.gz", [("repo-abc/logo.png", b"x", 0o644, REG)])
    result = unpack(built, tmp_path / "out")
    assert isinstance(result, Err)
    assert "nothing readable" in result.error


def sources(
    settings: GitHubAppSettings, handler: httpx.MockTransport, cache: Path | None = None, now: float = 0.0
) -> GitHubContextSources:
    return GitHubContextSources(httpx.AsyncClient(transport=handler), settings, cache, lambda: now)


async def test_a_public_repository_can_be_read_and_nothing_secret_is_sent(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"private": False})

    assert await sources(settings, httpx.MockTransport(handler)).check(OLLAMA) == ""


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (404, {}, "was not found, or it is not public"),
        (200, {"private": True}, "is private"),
        (403, {}, "asked to slow down"),
    ],
)
async def test_a_repository_that_cannot_be_read_says_why(
    settings: GitHubAppSettings, status: int, body: dict[str, object], expected: str
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    assert expected in await sources(settings, transport).check(OLLAMA)


async def test_a_repository_is_downloaded_unpacked_and_kept_for_the_next_step(
    settings: GitHubAppSettings, tmp_path: Path
) -> None:
    built = archive(tmp_path / "a.tar.gz", [("repo-abc/README.md", b"# hi\n", 0o644, REG)])
    downloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        downloads.append(request.url.path)
        assert "authorization" not in request.headers
        return httpx.Response(200, content=built.read_bytes())

    cache = tmp_path / "cache"
    reader = sources(settings, httpx.MockTransport(handler), cache, now=1000.0)
    first = await reader.copy_into(OLLAMA, tmp_path / "one")
    second = await reader.copy_into(OLLAMA, tmp_path / "two")
    assert (first, second) == (Ok(1), Ok(1))
    assert downloads == ["/repos/ollama/ollama/tarball/v1"]  # once, the second step used the copy
    assert (tmp_path / "two" / "README.md").read_text() == "# hi\n"


async def test_a_stale_copy_is_downloaded_again(settings: GitHubAppSettings, tmp_path: Path) -> None:
    built = archive(tmp_path / "a.tar.gz", [("repo-abc/README.md", b"# hi\n", 0o644, REG)])
    downloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        downloads.append(request.url.path)
        return httpx.Response(200, content=built.read_bytes())

    cache = tmp_path / "cache"
    await sources(settings, httpx.MockTransport(handler), cache, now=1000.0).copy_into(OLLAMA, tmp_path / "one")
    for marker in cache.rglob(".done"):
        os.utime(marker, (1000.0, 1000.0))
    await sources(settings, httpx.MockTransport(handler), cache, now=1000.0 + 4000).copy_into(OLLAMA, tmp_path / "two")
    assert len(downloads) == 2


async def test_a_missing_branch_or_tag_is_said(settings: GitHubAppSettings, tmp_path: Path) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    result = await sources(settings, transport).copy_into(OLLAMA, tmp_path / "out")
    assert isinstance(result, Err)
    assert "check the repository and the branch" in result.error
