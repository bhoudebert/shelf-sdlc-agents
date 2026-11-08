from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi.testclient import TestClient

from shelf.adapters.web.setup import create_setup_app

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
    assert "https://shelf.example.org" in page.text


def test_the_registration_page_posts_the_manifest_to_github() -> None:
    page = client().get("/setup/register")
    assert 'action="https://github.com/settings/apps/new"' in page.text
    assert "shelf.example.org/api/github/webhook" in page.text


def test_the_returned_code_is_traded_for_credentials_shown_once_and_never_cached() -> None:
    response = client().get("/setup/registered", params={"code": "abc"})
    assert "GITHUB_APP_ID=9" in response.text
    assert "GITHUB_APP_CLIENT_SECRET=cs" in response.text
    assert "A\\nB" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_a_visit_without_a_code_is_refused() -> None:
    assert client().get("/setup/registered").status_code == 400
