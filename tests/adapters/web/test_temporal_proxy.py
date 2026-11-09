from collections.abc import Callable
from dataclasses import replace

import httpx
import pytest

from shelf.adapters.web.context import WebSettings
from shelf.adapters.web.temporal_proxy import forwarded_headers, permitted
from shelf.domain.access import AccessRules
from tests.adapters.web.test_app import SETTINGS, Fixture

seen: list[httpx.Request] = []


def upstream(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    return httpx.Response(200, json={"namespaces": []}, headers={"set-cookie": "leak=1"})


def admin(settings: WebSettings = SETTINGS, handler: Callable[[httpx.Request], httpx.Response] = upstream) -> Fixture:
    seen.clear()
    fixture = Fixture(
        AccessRules(admins=frozenset({"alice"})), settings=settings, transport=httpx.MockTransport(handler)
    )
    fixture.sign_in()
    return fixture


def test_an_administrator_reads_temporal_through_the_proxy_without_leaking_shelfs_cookies() -> None:
    fixture = admin()
    response = fixture.client.get("/temporal/api/v1/namespaces?x=1")
    assert response.status_code == 200
    assert response.json() == {"namespaces": []}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "set-cookie" not in response.headers
    [request] = seen
    assert request.url.path == "/temporal/api/v1/namespaces"
    assert request.url.query == b"x=1"
    assert "cookie" not in request.headers
    assert request.headers["accept-encoding"] == "identity"


def test_an_ordinary_signed_in_person_is_refused() -> None:
    seen.clear()
    fixture = Fixture(transport=httpx.MockTransport(upstream))
    fixture.sign_in()
    assert fixture.client.get("/temporal/").status_code == 403
    assert not seen


def test_a_visitor_who_is_not_signed_in_is_sent_to_sign_in() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})), transport=httpx.MockTransport(upstream))
    response = fixture.client.get("/temporal/")
    assert (response.status_code, response.headers["location"]) == (303, "/")


def test_the_bare_path_goes_to_the_slash_form() -> None:
    response = admin().client.get("/temporal")
    assert (response.status_code, response.headers["location"]) == (308, "/temporal/")


def test_changing_workflows_is_refused_by_default_but_querying_is_allowed() -> None:
    fixture = admin()
    assert fixture.client.post("/temporal/api/v1/namespaces/default/workflows/w/terminate").status_code == 403
    assert fixture.client.post("/temporal/api/v1/namespaces/default/workflows/w/signal/decided").status_code == 403
    assert not seen
    assert fixture.client.post("/temporal/api/v1/namespaces/default/workflows/w/runs/r/query").status_code == 200
    assert len(seen) == 1


def test_writes_pass_only_when_the_operator_allows_them() -> None:
    fixture = admin(replace(SETTINGS, temporal_writable=True))
    assert fixture.client.post("/temporal/api/v1/namespaces/default/workflows/w/terminate").status_code == 200


def test_a_write_from_another_origin_is_refused_even_when_allowed() -> None:
    fixture = admin(replace(SETTINGS, temporal_writable=True))
    response = fixture.client.post(
        "/temporal/api/v1/namespaces/default/workflows/w/terminate", headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_the_proxy_does_not_exist_when_no_upstream_is_configured() -> None:
    fixture = admin(replace(SETTINGS, temporal_upstream=""))
    assert fixture.client.get("/temporal/").status_code == 404


def test_an_unreachable_temporal_is_reported_not_crashed() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        message = "refused"
        raise httpx.ConnectError(message)

    assert admin(handler=down).client.get("/temporal/").status_code == 502


@pytest.mark.parametrize(
    ("method", "path", "writable", "expected"),
    [
        ("GET", "/temporal/api/v1/namespaces", False, True),
        ("HEAD", "/temporal/", False, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/runs/r/query", False, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/query", False, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/query/__stack_trace", False, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/runs/r/query/snapshot", False, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/query/..", False, False),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/query/x/terminate", False, False),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/cancel", False, False),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/cancel", True, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/terminate", False, False),
        ("DELETE", "/temporal/api/v1/namespaces/n/schedules/s", False, False),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/signal/x", True, True),
        ("POST", "/temporal/api/v1/namespaces/n/workflows/w/query/../terminate", False, False),
    ],
)
def test_what_the_proxy_lets_through(method: str, path: str, *, writable: bool, expected: bool) -> None:
    assert permitted(method, path, writable=writable) is expected


def test_credentials_and_cookies_never_go_upstream() -> None:
    headers = {
        "Cookie": "shelf_session=x",
        "Authorization": "Bearer t",
        "Accept": "text/html",
        "Host": "shelf.example.org",
    }
    assert forwarded_headers(headers) == {"Accept": "text/html", "accept-encoding": "identity"}
