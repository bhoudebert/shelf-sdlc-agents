import html
import json
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi.testclient import TestClient

from shelf.entrypoints.setup import create_setup_app

PAYLOAD = {"id": 9, "slug": "shelf", "client_id": "Iv1.x", "client_secret": "cs", "webhook_secret": "ws", "pem": "A\nB"}


@asynccontextmanager
async def fake_github() -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json=PAYLOAD))
    ) as client:
        yield client


def client() -> TestClient:
    return TestClient(create_setup_app("https://shelf.example.org", fake_github))


def test_the_first_page_offers_one_click_registration() -> None:
    page = client().get("/")
    assert "Register on GitHub" in page.text
    assert "<code>https://shelf.example.org</code>" in page.text


def test_the_registration_page_posts_the_manifest_to_github() -> None:
    page = client().get("/setup/register")
    assert 'action="https://github.com/settings/apps/new"' in page.text
    manifest = json.loads(html.unescape(re.search(r'name="manifest" value="([^"]*)"', page.text).group(1)))  # type: ignore[union-attr]
    assert manifest["hook_attributes"]["url"] == "https://shelf.example.org/api/github/webhook"


def test_the_returned_code_is_traded_for_credentials_shown_once_and_never_cached() -> None:
    response = client().get("/setup/registered", params={"code": "abc"})
    assert "GITHUB_APP_ID=9" in response.text
    assert "GITHUB_APP_CLIENT_SECRET=cs" in response.text
    env_block = response.text.split('id="env-block"')[1].split("</pre>")[0]
    assert "BEGIN" not in env_block
    assert 'download="github-app.pem"' in response.text
    assert "data:application/x-pem-file;charset=utf-8,A%0AB" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_a_visit_without_a_code_is_refused() -> None:
    assert client().get("/setup/registered").status_code == 400


def test_the_setup_page_serves_the_styles_and_scripts_it_links_to() -> None:
    page = client()
    paths = re.findall(r'(?:href|src)="(/static/[^"]+)"', page.get("/").text)
    assert paths
    for path in paths:
        assert page.get(path).status_code == 200, path


def test_the_setup_health_check_reports_the_revision_it_runs() -> None:
    app = TestClient(create_setup_app("https://shelf.example.org", fake_github, revision="abc1234"))
    assert app.get("/healthz").json() == {"status": "setup", "revision": "abc1234"}
