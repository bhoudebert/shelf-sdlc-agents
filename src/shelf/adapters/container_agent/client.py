"""The worker's side of the runner: ask for a step over the runner's unix socket and hand back its lines."""

from collections.abc import AsyncIterator
from typing import Any

import httpx

from shelf.ports.step_runner import StepRequest


class RunnerError(RuntimeError):
    """The runner refused the request or could not be reached. The message says why, never what was in the request."""


def body_of(request: StepRequest) -> dict[str, Any]:
    """The runner's request for a ``StepRequest``: the fixed fields and nothing else."""
    body: dict[str, Any] = {
        "key": request.key,
        "kind": request.kind,
        "repo": request.repo,
        "clone": request.clone,
        "session": request.session,
        "mode": {"tools": "ro" if request.tools_readonly else "rw"},
        "env": dict(request.env),
        "input": dict(request.input),
    }
    if request.limits:
        body["limits"] = dict(request.limits)
    if request.docker:
        body["docker"] = True
    return body


class HttpStepRunner:
    """``StepRunner`` over HTTP. Pass a transport to test it without a socket."""

    def __init__(
        self,
        socket: str = "/run/shelf-runner/runner.sock",
        token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Reach the runner on ``socket`` with ``token``."""
        self._http = httpx.AsyncClient(
            base_url="http://runner",
            transport=transport or httpx.AsyncHTTPTransport(uds=socket),
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(30.0, read=None),
        )

    async def run(self, request: StepRequest) -> AsyncIterator[str]:
        """The lines of the step, as the runner streams them."""
        try:
            async with self._http.stream("POST", "/v1/steps", json=body_of(request)) as response:
                if not response.is_success:
                    detail = (await response.aread()).decode("utf-8", errors="replace")[:200]
                    message = f"the runner answered {response.status_code}: {detail}"
                    raise RunnerError(message)
                async for line in response.aiter_lines():
                    if line.strip():
                        yield line
        except httpx.HTTPError as error:
            message = f"the runner could not be reached: {type(error).__name__}"
            raise RunnerError(message) from None
