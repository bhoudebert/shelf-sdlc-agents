import io
import json
import struct
import tarfile
from collections.abc import AsyncIterator

import httpx
import pytest

from shelf.adapters.container_runner.engine import DockerEngine, stdout_of, tarball
from shelf.ports.container_engine import EngineError, Finished


def frame(stream: int, payload: bytes) -> bytes:
    return struct.pack(">BxxxI", stream, len(payload)) + payload


async def chunked(*pieces: bytes) -> AsyncIterator[bytes]:
    for piece in pieces:
        yield piece


async def test_only_standard_output_comes_out_of_the_log_frames_whatever_size_the_chunks_are() -> None:
    data = frame(1, b"one\n") + frame(2, b"error\n") + frame(1, b"two\n")
    pieces = [data[i : i + 3] for i in range(0, len(data), 3)]
    assert [part async for part in stdout_of(chunked(*pieces))] == [b"one\n", b"two\n"]


def test_the_task_file_is_for_the_step_user_only() -> None:
    with tarfile.open(fileobj=io.BytesIO(tarball("task.json", b"{}"))) as archive:
        [member] = archive.getmembers()
        assert (member.name, member.uid, member.gid, member.mode, member.size) == ("task.json", 1000, 1000, 0o400, 2)


def engine(handler: httpx.MockTransport) -> DockerEngine:
    return DockerEngine(transport=handler)


async def test_create_sends_the_spec_as_it_is_with_the_name_and_returns_the_id() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"Id": "abc"})

    assert await engine(httpx.MockTransport(handle)).create({"Image": "x"}, "shelf-step-1") == "abc"
    [request] = seen
    assert (request.url.path, request.url.params["name"], json.loads(request.content)) == (
        "/containers/create",
        "shelf-step-1",
        {"Image": "x"},
    )


async def test_the_file_goes_to_the_archive_endpoint_of_the_container() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    await engine(httpx.MockTransport(handle)).put_file("abc", "/run/shelf", "task.json", b"{}")
    [request] = seen
    assert (request.method, request.url.path, request.url.params["path"]) == (
        "PUT",
        "/containers/abc/archive",
        "/run/shelf",
    )


async def test_wait_says_whether_memory_killed_the_container() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/wait"):
            return httpx.Response(200, json={"StatusCode": 137})
        return httpx.Response(200, json={"State": {"OOMKilled": True}})

    assert await engine(httpx.MockTransport(handle)).wait("abc") == Finished(137, oom=True)


async def test_logs_are_followed_and_demultiplexed() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["follow"] == "1"
        return httpx.Response(200, stream=httpx.ByteStream(frame(1, b"a\n") + frame(2, b"e\n")))

    got = [part async for part in engine(httpx.MockTransport(handle)).stdout("abc")]
    assert got == [b"a\n"]


async def test_killing_or_removing_what_is_already_gone_is_not_an_error() -> None:
    gone = engine(httpx.MockTransport(lambda request: httpx.Response(404)))
    await gone.kill("abc")
    await gone.remove("abc")


async def test_owned_asks_only_for_the_runners_label() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"Id": "x", "Labels": {"shelf.expires": "5"}}])

    [found] = await engine(httpx.MockTransport(handle)).owned()
    assert json.loads(seen[0].url.params["filters"]) == {"label": ["shelf.managed=true"]}
    assert (found.id, found.labels) == ("x", {"shelf.expires": "5"})


async def test_an_engine_error_names_the_call_and_never_the_body() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="ANTHROPIC_API_KEY=sk-secret")

    with pytest.raises(EngineError) as caught:
        await engine(httpx.MockTransport(handle)).create({"Env": ["ANTHROPIC_API_KEY=sk-secret"]}, "n")
    assert "sk-secret" not in str(caught.value)
    assert "500" in str(caught.value)


async def test_an_engine_that_cannot_be_reached_says_so() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        message = "no socket at /secret/path"
        raise httpx.ConnectError(message)

    with pytest.raises(EngineError, match="could not be reached: ConnectError") as caught:
        await engine(httpx.MockTransport(handle)).owned()
    assert "/secret/path" not in str(caught.value)
