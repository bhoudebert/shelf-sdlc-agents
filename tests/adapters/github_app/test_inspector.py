import httpx

from shelf.adapters.github_app.inspector import GitHubAppInspector
from shelf.adapters.github_app.settings import GitHubAppSettings
from shelf.domain.result import Err, Ok


def inspector(settings: GitHubAppSettings, handler: httpx.MockTransport) -> GitHubAppInspector:
    return GitHubAppInspector(httpx.AsyncClient(transport=handler), settings)


async def test_it_reads_events_permissions_webhook_and_deliveries_as_the_app(settings: GitHubAppSettings) -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["Authorization"].split(".")[0]))
        match request.url.path:
            case "/app":
                return httpx.Response(200, json={"events": ["pull_request"], "permissions": {"issues": "write"}})
            case "/app/hook/config":
                return httpx.Response(200, json={"url": "https://x.example/api/github/webhook", "secret": "********"})
            case _:
                return httpx.Response(
                    200, json=[{"event": "issue_comment", "status_code": 202, "delivered_at": "2026-11-08T20:00:00Z"}]
                )

    result = await inspector(settings, httpx.MockTransport(handler)).facts()
    assert isinstance(result, Ok)
    assert result.value.events == frozenset({"pull_request"})
    assert result.value.permissions == {"issues": "write"}
    assert result.value.webhook_url == "https://x.example/api/github/webhook"
    assert result.value.webhook_secret_set
    assert [(d.event, d.status_code) for d in result.value.deliveries] == [("issue_comment", 202)]
    assert [path for path, _ in seen] == ["/app", "/app/hook/config", "/app/hook/deliveries"]
    assert all(bearer.startswith("Bearer ") for _, bearer in seen)


async def test_a_webhook_with_no_secret_and_no_deliveries_is_read_as_such(settings: GitHubAppSettings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/hook/deliveries":
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"events": [], "permissions": {}, "url": None, "secret": None})

    result = await inspector(settings, httpx.MockTransport(handler)).facts()
    assert isinstance(result, Ok)
    assert (result.value.webhook_url, result.value.webhook_secret_set, result.value.deliveries) == ("", False, ())


async def test_an_app_identity_github_refuses_is_explained(settings: GitHubAppSettings) -> None:
    result = await inspector(settings, httpx.MockTransport(lambda _r: httpx.Response(401))).facts()
    assert isinstance(result, Err)
    assert "GITHUB_APP_ID" in result.error


async def test_an_unreachable_github_is_reported_without_a_traceback(settings: GitHubAppSettings) -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        message = "no route"
        raise httpx.ConnectError(message)

    result = await inspector(settings, httpx.MockTransport(down)).facts()
    assert isinstance(result, Err)
    assert "could not be reached" in result.error
