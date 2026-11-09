"""Public repositories read as reference material: downloaded as a plain archive and unpacked here, never run.

No git is involved, so nothing a repository carries can act while it is copied: no hooks, no submodules, no filters, no
links. Only regular text files are written, each read only, size and count are capped, and nothing is executed.
"""

import hashlib
import os
import shutil
import tarfile
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.context_repo import ContextRepo
from shelf.domain.result import Err, Ok, Result

MAX_DOWNLOAD = 60_000_000
"""The most that is downloaded for one repository, compressed."""
MAX_FILE = 1_000_000
"""A larger file is skipped: reference material is text a person reads."""
MAX_TOTAL = 40_000_000
MAX_FILES = 5_000
CACHE_SECONDS = 3600.0
NOT_FOUND = 404
RATE_LIMITED = 403
SKIPPED_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".xz",
        ".bz2",
        ".7z",
        ".jar",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".bin",
        ".class",
        ".wasm",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".mp3",
        ".mp4",
        ".mov",
        ".onnx",
        ".gguf",
        ".safetensors",
        ".pt",
        ".pth",
        ".npy",
        ".parquet",
        ".db",
        ".sqlite",
    }
)
"""Binary things: nothing a person reads as a reference, and the ones that could be run."""


@dataclass(frozen=True, slots=True)
class GitHubContextSources:
    """The ``ContextSources`` port over GitHub, for repositories that are public. No credential is sent."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    cache: Path | None = None
    """Where copies are kept for an hour, so that the steps of one piece of work download a repository once."""
    clock: Callable[[], float] = time.time

    async def check(self, item: ContextRepo) -> str:
        """Why the repository cannot be read: missing, not public, or GitHub asking to slow down."""
        response = await self.client.get(f"{self.settings.api_url}/repos/{item.repo.full_name}")
        if response.status_code == NOT_FOUND:
            return f"{item.repo.full_name} was not found, or it is not public"
        if response.status_code == RATE_LIMITED:
            return "GitHub asked to slow down: try again in a few minutes"
        response.raise_for_status()
        if response.json().get("private"):
            return f"{item.repo.full_name} is private: only public repositories can be read this way"
        return ""

    async def copy_into(self, item: ContextRepo, destination: Path) -> Result[int, str]:
        """Read-only copies of the repository's text files in ``destination``, from the cache while it is fresh."""
        kept = self._cached(item)
        if kept is not None:
            shutil.copytree(kept, destination, dirs_exist_ok=True)
            return Ok(sum(1 for path in kept.rglob("*") if path.is_file()))
        with tempfile.TemporaryDirectory(prefix="shelf-context-") as scratch:
            archive = Path(scratch) / "repo.tar.gz"
            problem = await self._download(item, archive)
            if problem:
                return Err(problem)
            fresh = Path(scratch) / "files"
            copied = unpack(archive, fresh, item.path)
            if isinstance(copied, Err):
                return copied
            self._keep(item, fresh)
            shutil.copytree(fresh, destination, dirs_exist_ok=True)
            return copied

    async def _download(self, item: ContextRepo, archive: Path) -> str:
        ref = f"/{item.ref}" if item.ref else ""
        url = f"{self.settings.api_url}/repos/{item.repo.full_name}/tarball{ref}"
        async with self.client.stream("GET", url, follow_redirects=True) as response:
            if response.status_code == NOT_FOUND:
                return f"{item.spec} was not found: check the repository and the branch, tag or commit"
            if response.status_code == RATE_LIMITED:
                return "GitHub asked to slow down: try again in a few minutes"
            response.raise_for_status()
            received = 0
            with archive.open("wb") as out:
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    if received > MAX_DOWNLOAD:
                        size = MAX_DOWNLOAD // 1_000_000
                        return (
                            f"{item.repo.full_name} is larger than {size} MB: name a folder, such as {item.spec}:docs"
                        )
                    out.write(chunk)
        return ""

    def _folder(self, item: ContextRepo) -> Path | None:
        if self.cache is None:
            return None
        return (
            self.cache / f"{item.directory}__{hashlib.sha1(item.spec.encode(), usedforsecurity=False).hexdigest()[:10]}"
        )

    def _cached(self, item: ContextRepo) -> Path | None:
        folder = self._folder(item)
        marker = folder / ".done" if folder else None
        if folder and marker and marker.is_file() and self.clock() - marker.stat().st_mtime < CACHE_SECONDS:
            return folder / "files"
        return None

    def _keep(self, item: ContextRepo, files: Path) -> None:
        folder = self._folder(item)
        if folder is None:
            return
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copytree(files, folder / "files")
        (folder / ".done").write_text("ok")
        os.utime(folder / ".done", (self.clock(), self.clock()))


def unpack(archive: Path, destination: Path, only: str = "") -> Result[int, str]:
    """Write the text files of a repository archive into ``destination``, and nothing else.

    Links, devices and anything that is not a regular file are skipped, names that leave the folder are skipped, each
    file is written read only without any execute bit, and size and count are capped.
    """
    destination.mkdir(parents=True, exist_ok=True)
    wanted = PurePosixPath(only) if only else None
    files = total = 0
    with tarfile.open(archive, mode="r:gz") as tar:
        for member in tar:
            relative = _relative(member.name)
            if relative is None or not member.isreg() or member.size > MAX_FILE or not _inside(relative, wanted):
                continue
            if relative.suffix.lower() in SKIPPED_SUFFIXES or files >= MAX_FILES or total + member.size > MAX_TOTAL:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            data = source.read(MAX_FILE + 1)
            if b"\0" in data[:8192]:  # binary
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
            with os.fdopen(descriptor, "wb") as out:
                out.write(data)
            files += 1
            total += len(data)
    if files == 0:
        return Err("nothing readable was found there" + (f" under {only}" if only else ""))
    return Ok(files)


def _relative(name: str) -> PurePosixPath | None:
    """The path of an archive member without its top folder, or ``None`` when it would leave the folder."""
    parts = PurePosixPath(name).parts
    if len(parts) < 2 or PurePosixPath(name).is_absolute() or ".." in parts:  # noqa: PLR2004
        return None
    return PurePosixPath(*parts[1:])


def _inside(path: PurePosixPath, wanted: PurePosixPath | None) -> bool:
    return wanted is None or path == wanted or wanted in path.parents
