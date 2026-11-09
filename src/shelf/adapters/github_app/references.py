"""Issues, pull requests and files of a repository, read as the App to start a piece of work from them."""

from dataclasses import dataclass

import httpx

from shelf.adapters.github_app.pulls import TokenFor
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.model import RepoRef
from shelf.domain.reference import MAX_BYTES, TRUSTED_AUTHORS, File, Imported, Reference, Thread
from shelf.domain.result import Err, Ok, Result

NOT_FOUND = 404


@dataclass(frozen=True, slots=True)
class GitHubReferences:
    """The ``References`` port over GitHub."""

    client: httpx.AsyncClient
    settings: GitHubAppSettings
    token_for: TokenFor

    async def read(self, repo: RepoRef, reference: Reference) -> Result[Imported, str]:
        """The text of the reference, or why it cannot be used."""
        if isinstance(reference, Thread):
            return await self._thread(repo, reference)
        return await self._file(repo, reference)

    async def _thread(self, repo: RepoRef, thread: Thread) -> Result[Imported, str]:
        response = await self._get(repo, f"/repos/{repo.full_name}/issues/{thread.number}")
        if response.status_code == NOT_FOUND:
            return Err(f"{repo.full_name} has no issue or pull request #{thread.number}")
        response.raise_for_status()
        body = response.json()
        if body.get("author_association") not in TRUSTED_AUTHORS:
            return Err(
                f"#{thread.number} was written by someone without write access to {repo.full_name}: "
                "paste the text you trust instead"
            )
        text = f"# {body.get('title', '')}\n\n{body.get('body') or ''}"
        return _bounded(Imported(f"#{thread.number}", text))

    async def _file(self, repo: RepoRef, file: File) -> Result[Imported, str]:
        params = {"ref": file.ref} if file.ref else {}
        response = await self._get(
            repo, f"/repos/{repo.full_name}/contents/{file.path}", params, accept="application/vnd.github.raw+json"
        )
        where = f"{file.path}" + (f" at {file.ref}" if file.ref else " on the default branch")
        if response.status_code == NOT_FOUND:
            return Err(f"{repo.full_name} has no file {where}")
        response.raise_for_status()
        if response.headers.get("content-type", "").startswith("application/json"):
            return Err(f"{file.path} is a folder: point at one file")
        if len(response.content) > MAX_BYTES:
            return Err(f"{file.path} is longer than {MAX_BYTES // 1000} KB: point at a shorter document")
        try:
            text = response.content.decode("utf-8")
        except UnicodeDecodeError:
            return Err(f"{file.path} is not a text file")
        return Ok(Imported(file.path, text))

    async def _get(
        self,
        repo: RepoRef,
        path: str,
        params: dict[str, str] | None = None,
        accept: str = "application/vnd.github+json",
    ) -> httpx.Response:
        token = await self.token_for(repo)
        return await self.client.get(
            f"{self.settings.api_url}{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": accept,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )


def _bounded(imported: Imported) -> Result[Imported, str]:
    if len(imported.text.encode()) > MAX_BYTES:
        return Err(f"{imported.source} is longer than {MAX_BYTES // 1000} KB: paste the part that matters")
    return Ok(imported)
