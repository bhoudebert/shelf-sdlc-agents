import json
from typing import Any

import httpx
import pytest

from shelf.adapters.container_runner.app import create_app
from shelf.adapters.container_runner.service import StepService
from shelf.domain.stepspec import RunnerRules
from shelf.domain.stepstream import Exit, Hello, Result, decode, encode
from tests.adapters.container_runner.fakes import FakeEngine

RULES = RunnerRules(image="shelf-step:test")
AUTH = {"Authorization": "Bearer secret"}


def body(**changes: Any) -> dict[str, Any]:
    return {
        "key": "wf-1/implement/1",
        "repo": "acme/shop",
        "clone": "steps/wf-1",
        "env": {"GH_TOKEN": "t"},
        "input": {"prompt": "go"},
        **changes,
    }


def client(engine: FakeEngine, token: str | None = "secret") -> httpx.AsyncClient:
    app = create_app(StepService(engine, RULES, ping_every=0.05), RULES, token)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://runner")


def good_engine() -> FakeEngine:
    return FakeEngine([(encode(Hello()) + "\n" + encode(Result(result="done")) + "\n").encode()])


async def test_a_step_streams_as_lines_and_ends_with_the_runners_exit() -> None:
    async with client(good_engine()) as http:
        response = await http.post("/v1/steps", json=body(), headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    found = [decode(line) for line in response.text.splitlines()]
    assert [type(event).__name__ for event in found] == ["Hello", "Result", "Exit"]
    assert found[-1] == Exit(0)


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "secret"}])
async def test_a_request_without_the_callers_token_is_not_allowed_and_starts_nothing(headers: dict[str, str]) -> None:
    engine = good_engine()
    async with client(engine) as http:
        post = await http.post("/v1/steps", json=body(), headers=headers)
        get = await http.get("/v1/steps/wf-1/implement/1", headers=headers)
        delete = await http.delete("/v1/steps/wf-1/implement/1", headers=headers)
    assert (post.status_code, get.status_code, delete.status_code) == (401, 401, 401)
    assert engine.created == []


async def test_an_engine_option_in_the_request_is_refused_and_starts_nothing() -> None:
    engine = good_engine()
    async with client(engine) as http:
        response = await http.post("/v1/steps", json=body(privileged=True), headers=AUTH)
    assert response.status_code == 422
    assert "privileged" in response.json()["detail"]
    assert engine.created == []


async def test_a_refusal_never_repeats_the_secret_it_was_sent() -> None:
    async with client(good_engine()) as http:
        response = await http.post("/v1/steps", json=body(env={"PATH": "sk-secret"}), headers=AUTH)
    assert response.status_code == 422
    assert "sk-secret" not in response.text


async def test_a_body_that_is_not_json_is_refused() -> None:
    async with client(good_engine()) as http:
        response = await http.post("/v1/steps", content=b"{nope", headers=AUTH)
    assert response.status_code == 422


async def test_the_state_and_the_events_can_be_read_again_after_the_step_is_over() -> None:
    async with client(good_engine()) as http:
        await http.post("/v1/steps", json=body(), headers=AUTH)
        state = (await http.get("/v1/steps/wf-1/implement/1", headers=AUTH)).json()
        again = await http.get("/v1/steps/wf-1/implement/1/events", params={"cursor": 1}, headers=AUTH)
    assert (state["state"], state["lines"], state["exit"]) == ("done", 3, {"code": 0, "reason": ""})
    assert [json.loads(line)["e"] for line in again.text.splitlines()] == ["result", "exit"]


async def test_an_unknown_step_is_not_found() -> None:
    async with client(good_engine()) as http:
        assert (await http.get("/v1/steps/nope", headers=AUTH)).status_code == 404
        assert (await http.get("/v1/steps/nope/events", headers=AUTH)).status_code == 404
        assert (await http.delete("/v1/steps/nope", headers=AUTH)).status_code == 404


async def test_deleting_a_finished_step_says_it_is_done() -> None:
    async with client(good_engine()) as http:
        await http.post("/v1/steps", json=body(), headers=AUTH)
        stopped = await http.delete("/v1/steps/wf-1/implement/1", headers=AUTH)
    assert stopped.json()["state"] == "done"


async def test_no_documentation_pages_are_served() -> None:
    async with client(good_engine()) as http:
        assert (await http.get("/docs", headers=AUTH)).status_code == 404
        assert (await http.get("/openapi.json", headers=AUTH)).status_code == 404


async def test_a_runner_made_for_tests_can_run_without_a_token() -> None:
    async with client(good_engine(), token=None) as http:
        assert (await http.post("/v1/steps", json=body())).status_code == 200
