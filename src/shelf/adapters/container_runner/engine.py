"""The engine over its unix socket: the Docker Engine API, by hand, with ``httpx``. No SDK, no shell, no CLI."""

import io
import json
import struct
import tarfile
from collections.abc import AsyncIterator, Mapping
from typing import Any, Final

import httpx

from shelf.ports.container_engine import EngineError, Finished, Owned

HEADER: Final = struct.Struct(">BxxxI")
"""The frame header of a log stream without a terminal: the stream (1 output, 2 error), three zeros, the size."""
STDOUT: Final = 1
OK: Final = 200
MANAGED: Final = "shelf.managed=true"


async def stdout_of(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """The standard-output payloads of an engine log stream, whatever size the chunks arrive in."""
    pending = b""
    async for chunk in chunks:
        pending += chunk
        while len(pending) >= HEADER.size:
            stream, size = HEADER.unpack(pending[: HEADER.size])
            if len(pending) < HEADER.size + size:
                break
            payload = pending[HEADER.size : HEADER.size + size]
            pending = pending[HEADER.size + size :]
            if stream == STDOUT:
                yield payload


def tarball(name: str, data: bytes) -> bytes:
    """A tar archive holding one file for the step's user (uid 1000), mode 0400."""
    info = tarfile.TarInfo(name)
    info.size, info.mode, info.uid, info.gid = len(data), 0o400, 1000, 1000
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as archive:
        archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


class DockerEngine:
    """``ContainerEngine`` over the Docker Engine API. Pass a transport to test it without a daemon."""

    def __init__(self, socket: str = "/var/run/docker.sock", transport: httpx.AsyncBaseTransport | None = None) -> None:
        """Talk to the engine on ``socket``."""
        self._http = httpx.AsyncClient(
            base_url="http://engine",
            transport=transport or httpx.AsyncHTTPTransport(uds=socket),
            timeout=httpx.Timeout(30.0, read=None),
        )

    async def _send(  # noqa: PLR0913
        self,
        method: str,
        path: str,
        *,
        ok: tuple[int, ...] = (200, 201, 204),
        params: Mapping[str, str | int] | None = None,
        body: Mapping[str, Any] | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self._http.request(
                method, path, params=params, json=body, content=content, headers=headers
            )
        except httpx.HTTPError as error:
            message = f"the container engine could not be reached: {type(error).__name__}"
            raise EngineError(message) from None
        if response.status_code not in ok:
            message = f"the container engine answered {response.status_code} to {method} {path.split('/')[1]}"
            raise EngineError(message)
        return response

    async def create(self, spec: Mapping[str, Any], name: str) -> str:
        """Create the container."""
        response = await self._send("POST", "/containers/create", params={"name": name}, body=dict(spec))
        return str(response.json()["Id"])

    async def put_file(self, container: str, directory: str, name: str, data: bytes) -> None:
        """Put one file into a directory of the container."""
        await self._send(
            "PUT",
            f"/containers/{container}/archive",
            params={"path": directory},
            content=tarball(name, data),
            headers={"Content-Type": "application/x-tar"},
        )

    async def start(self, container: str) -> None:
        """Start the container."""
        await self._send("POST", f"/containers/{container}/start", ok=(204, 304))

    async def stdout(self, container: str) -> AsyncIterator[bytes]:
        """Follow the container's standard output."""
        request = self._http.build_request(
            "GET", f"/containers/{container}/logs", params={"stdout": 1, "stderr": 1, "follow": 1}
        )
        try:
            response = await self._http.send(request, stream=True)
        except httpx.HTTPError as error:
            message = f"the container engine could not be reached: {type(error).__name__}"
            raise EngineError(message) from None
        try:
            if response.status_code != OK:
                message = f"the container engine answered {response.status_code} to logs"
                raise EngineError(message)
            async for payload in stdout_of(response.aiter_raw()):
                yield payload
        finally:
            await response.aclose()

    async def wait(self, container: str) -> Finished:
        """Wait for the container to stop, and say whether memory killed it."""
        response = await self._send("POST", f"/containers/{container}/wait", params={"condition": "not-running"})
        code = int(response.json().get("StatusCode", -1))
        state = (await self._send("GET", f"/containers/{container}/json")).json().get("State", {})
        return Finished(code, oom=bool(state.get("OOMKilled")))

    async def kill(self, container: str) -> None:
        """Kill the container; one already gone is fine."""
        await self._send("POST", f"/containers/{container}/kill", ok=(204, 404, 409))

    async def remove(self, container: str) -> None:
        """Remove the container and its anonymous volumes."""
        await self._send("DELETE", f"/containers/{container}", params={"force": 1, "v": 1}, ok=(204, 404))

    async def runtimes(self) -> list[str]:
        """The runtimes the engine reports in its info."""
        response = await self._send("GET", "/info")
        return list(response.json().get("Runtimes") or {})

    async def owned(self) -> list[Owned]:
        """The containers that carry the runner's label."""
        filters = json.dumps({"label": [MANAGED]})
        response = await self._send("GET", "/containers/json", params={"all": 1, "filters": filters})
        return [Owned(str(item["Id"]), dict(item.get("Labels") or {})) for item in response.json()]
