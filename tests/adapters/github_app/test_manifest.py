import httpx

from shelf.adapters.github_app.manifest import (
    EVENTS,
    PERMISSIONS,
    Registered,
    app_manifest,
    convert,
    registration_form,
    settings_from,
)


def test_the_manifest_derives_every_url_from_the_public_address() -> None:
    manifest = app_manifest("https://shelf.example.org/")
    assert manifest["callback_urls"] == ["https://shelf.example.org/auth/callback"]
    assert manifest["hook_attributes"]["url"] == "https://shelf.example.org/api/github/webhook"
    assert manifest["default_permissions"] == PERMISSIONS
    assert manifest["default_events"] == EVENTS
    assert manifest["public"] is False


def test_the_manifest_lists_only_events_github_lets_an_app_subscribe_to() -> None:
    always_sent = {"installation", "installation_repositories", "ping"}
    assert not always_sent & set(app_manifest("https://shelf.example.org")["default_events"])


def test_every_subscribed_event_is_covered_by_a_requested_permission() -> None:
    needs = {"pull_request": "pull_requests", "issue_comment": "issues"}
    manifest = app_manifest("https://shelf.example.org")
    assert set(manifest["default_events"]) == set(needs)
    assert all(permission in manifest["default_permissions"] for permission in needs.values())


def test_the_registration_form_posts_the_escaped_manifest_to_github() -> None:
    page = registration_form("https://shelf.example.org")
    assert 'action="https://github.com/settings/apps/new"' in page
    assert "&quot;name&quot;" in page
    assert '"name"' not in page


async def test_a_registration_code_is_converted_into_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/app-manifests/abc/conversions"
        return httpx.Response(
            201,
            json={
                "id": 9,
                "slug": "shelf",
                "client_id": "Iv1.x",
                "client_secret": "s",
                "webhook_secret": "w",
                "pem": "PEM",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        registered = await convert(client, "abc")
    assert registered == Registered("9", "shelf", "Iv1.x", "s", "w", "PEM")
    assert settings_from(registered).app_id == "9"
