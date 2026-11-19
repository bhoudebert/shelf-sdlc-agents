"""The runner's HTTP surface: a fixed set of routes behind the caller's token, on a unix socket."""

import hmac
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from shelf.adapters.container_runner.service import StepRecord, StepService
from shelf.domain.result import Err
from shelf.domain.stepspec import RunnerRules, parse_request

LINES = "application/x-ndjson"


def _lines(service: StepService, record: StepRecord, cursor: int = 0) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        async for line in service.follow(record, cursor):
            yield line + "\n"

    return StreamingResponse(generate(), media_type=LINES)


def _record(service: StepService, key: str) -> StepRecord:
    record = service.known(key)
    if record is None:
        raise HTTPException(status_code=404, detail="no such step")
    return record


def _starting(service: StepService, rules: RunnerRules, guard: list[Any]) -> APIRouter:
    router = APIRouter(dependencies=guard)

    @router.post("/v1/steps")
    async def start(request: Request) -> Response:
        try:
            body: Any = await request.json()
        except ValueError:
            return JSONResponse({"detail": "the request is not JSON"}, status_code=422)
        parsed = parse_request(body, rules)
        if isinstance(parsed, Err):
            return JSONResponse({"detail": parsed.error}, status_code=422)
        return _lines(service, service.start(parsed.value))

    return router


def _following(service: StepService, guard: list[Any]) -> APIRouter:
    router = APIRouter(dependencies=guard)

    @router.get("/v1/steps/{key:path}/events")
    async def events(key: str, cursor: int = 0) -> StreamingResponse:
        return _lines(service, _record(service, key), cursor)

    @router.get("/v1/steps/{key:path}")
    async def state(key: str) -> dict[str, Any]:
        record = _record(service, key)
        end = record.exit
        return {
            "key": key,
            "state": "done" if record.done else "running",
            "lines": len(record.lines),
            "exit": None if end is None else {"code": end.code, "reason": end.reason},
            "started": record.started,
            "finished": record.finished or None,
        }

    @router.delete("/v1/steps/{key:path}")
    async def stop(key: str) -> dict[str, str]:
        record = _record(service, key)
        await service.stop(record)
        return {"key": key, "state": "done" if record.done else "stopping"}

    return router


def create_app(service: StepService, rules: RunnerRules, token: str | None) -> FastAPI:
    """The runner's app. Every route needs ``token``, the secret the worker sends; ``None`` is for tests only."""
    app = FastAPI(title="shelf runner", docs_url=None, redoc_url=None, openapi_url=None)

    def allowed(authorization: Annotated[str, Header()] = "") -> None:
        if token is None:
            return
        scheme, _, given = authorization.partition(" ")
        if scheme != "Bearer" or not token or not hmac.compare_digest(given.strip().encode(), token.encode()):
            raise HTTPException(status_code=401, detail="not allowed")

    guard = [Depends(allowed)]
    app.include_router(_starting(service, rules, guard))
    app.include_router(_following(service, guard))
    return app
