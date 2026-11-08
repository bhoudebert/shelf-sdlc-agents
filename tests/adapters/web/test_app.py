import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from shelf.adapters.web.app import create_app
from shelf.adapters.web.context import WebDeps, WebSettings
from shelf.adapters.web.sessions import SessionStore
from shelf.domain.access import AccessRules
from shelf.domain.config import RepoConfig, Role
from shelf.domain.model import Identity, RepoRef, WorkId, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.work import DecisionKind, PersonDecided, Reason
from tests.fakes import FakeConfigs, FakeForge, FakeRunner

REPO = RepoRef("acme", "shop")
SETTINGS = WebSettings(
    "https://shelf.example.org",
    "shelf",
    "Iv1.client",
    "hook-secret",
    "k" * 32,
    revision="abc1234",
    temporal_upstream="http://temporal:8233",
)
ALICE = Identity("alice", frozenset({"acme"}))


class Fixture:
    def __init__(
        self,
        rules: AccessRules | None = None,
        configs: FakeConfigs | None = None,
        settings: WebSettings = SETTINGS,
        transport: httpx.MockTransport | None = None,
    ) -> None:
        self.forge = FakeForge(identities={"token-code": ALICE}, repos={"token-code": (REPO,)})
        self.runner = FakeRunner()
        deps = WebDeps(
            settings,
            rules or AccessRules(),
            self.forge,
            self.runner,
            configs or FakeConfigs(),
            SessionStore(),
            transport,
        )
        self.client = TestClient(create_app(deps), base_url="https://shelf.example.org", follow_redirects=False)

    def sign_in(self) -> None:
        started = self.client.get("/auth/login")
        state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
        self.client.get("/auth/callback", params={"code": "code", "state": state})


@pytest.fixture
def app() -> Fixture:
    return Fixture()


def test_the_home_page_offers_to_sign_in_with_github(app: Fixture) -> None:
    page = app.client.get("/")
    assert page.status_code == 200
    assert "/auth/login" in page.text


def test_signing_in_starts_an_oauth_round_trip_to_github(app: Fixture) -> None:
    response = app.client.get("/auth/login")
    location = urlparse(response.headers["location"])
    assert (location.netloc, location.path) == ("github.com", "/login/oauth/authorize")
    query = parse_qs(location.query)
    assert query["client_id"] == ["Iv1.client"]
    assert query["redirect_uri"] == ["https://shelf.example.org/auth/callback"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


def test_a_callback_that_did_not_start_here_is_refused(app: Fixture) -> None:
    assert app.client.get("/auth/callback", params={"code": "c", "state": "forged"}).status_code == 400


def test_a_person_on_the_list_signs_in_and_reaches_the_board(app: Fixture) -> None:
    app.sign_in()
    page = app.client.get("/board")
    assert page.status_code == 200
    assert "alice" in page.text


def test_a_person_off_the_list_is_told_so() -> None:
    app = Fixture(AccessRules(users=frozenset({"bob"})))
    started = app.client.get("/auth/login")
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    response = app.client.get("/auth/callback", params={"code": "code", "state": state})
    assert "access list" in response.text
    assert app.client.get("/board").status_code == 303


def test_pages_that_need_a_session_send_visitors_to_sign_in(app: Fixture) -> None:
    for path in ("/board", "/start", "/work/work-1"):
        response = app.client.get(path)
        assert (response.status_code, response.headers["location"]) == (303, "/")


def test_a_person_without_repositories_is_shown_how_to_install_the_app() -> None:
    app = Fixture()
    app.forge.repos = {}
    app.sign_in()
    assert "https://github.com/apps/shelf/installations/new" in app.client.get("/board").text


def test_starting_work_creates_it_and_shows_its_page(app: Fixture) -> None:
    app.sign_in()
    response = app.client.post("/start", data={"repo": "acme/shop", "entry": "need", "text": "loyalty points"})
    assert (response.status_code, response.headers["location"]) == (303, "/work/work-1")
    assert "acme/shop" in app.client.get("/work/work-1").text


@pytest.mark.parametrize(
    ("form", "status"),
    [
        ({"repo": "acme/shop", "entry": "need", "text": " "}, 422),
        ({"repo": "nonsense", "entry": "need", "text": "x"}, 422),
        ({"repo": "acme/shop", "entry": "teleport", "text": "x"}, 422),
        ({"repo": "acme/secret", "entry": "need", "text": "x"}, 404),
    ],
)
def test_a_bad_start_is_answered_on_the_form(app: Fixture, form: dict[str, str], status: int) -> None:
    app.sign_in()
    assert app.client.post("/start", data=form).status_code == status


def test_a_request_from_another_origin_is_refused(app: Fixture) -> None:
    app.sign_in()
    response = app.client.post(
        "/start", data={"repo": "acme/shop", "entry": "need", "text": "x"}, headers={"origin": "https://evil.example"}
    )
    assert response.status_code == 403


def test_work_on_an_invisible_repository_is_not_found(app: Fixture) -> None:
    app.sign_in()
    app.runner.views[WorkId("work-9")] = WorkView(
        WorkId("work-9"), RepoRef("acme", "secret"), "x", EntryPoint.NEED, Phase.INTAKE
    )
    assert app.client.get("/work/work-9").status_code == 404


def waiting(app: Fixture) -> None:
    app.sign_in()
    app.runner.views[WorkId("work-1")] = WorkView(
        WorkId("work-1"), REPO, "alice", EntryPoint.NEED, Phase.SPEC_APPROVAL, waiting_for=Reason.GATE
    )


def test_a_decision_reaches_the_work(app: Fixture) -> None:
    waiting(app)
    response = app.client.post("/work/work-1/decide", data={"kind": "approve", "note": ""})
    assert response.status_code == 200
    assert app.runner.decisions == [(WorkId("work-1"), PersonDecided("alice", DecisionKind.APPROVE))]


def test_a_decision_by_someone_without_the_role_is_refused() -> None:
    configs = FakeConfigs({REPO: RepoConfig(roles={Role.PRODUCT_OWNER: frozenset({"carol"})})})
    app = Fixture(configs=configs)
    waiting(app)
    response = app.client.post("/work/work-1/decide", data={"kind": "approve"})
    assert response.status_code == 403
    assert app.runner.decisions == []


def test_an_unknown_decision_is_refused(app: Fixture) -> None:
    waiting(app)
    assert app.client.post("/work/work-1/decide", data={"kind": "explode"}).status_code == 422


def test_the_work_panel_offers_the_buttons_that_fit_the_wait(app: Fixture) -> None:
    waiting(app)
    panel = app.client.get("/work/work-1/panel").text
    assert "Approve" in panel
    assert "Request changes" in panel
    assert "Resume" not in panel


def test_signing_out_ends_the_session(app: Fixture) -> None:
    app.sign_in()
    assert app.client.post("/auth/logout").status_code == 303
    assert app.client.get("/board").status_code == 303


def signed(body: bytes, secret: str = "hook-secret") -> dict[str, str]:
    return {"x-hub-signature-256": "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()}


def post_hook(
    app: Fixture, event: str, payload: Mapping[str, object], headers: Callable[[bytes], dict[str, str]] = signed
) -> int:
    body = json.dumps(payload).encode()
    return app.client.post(
        "/api/github/webhook", content=body, headers={**headers(body), "x-github-event": event}
    ).status_code


def test_a_webhook_with_a_bad_signature_is_refused(app: Fixture) -> None:
    assert post_hook(app, "pull_request", {}, lambda body: signed(body, "wrong")) == 401


def test_a_merged_pull_request_is_signalled_to_its_work(app: Fixture) -> None:
    payload = {"action": "closed", "pull_request": {"merged": True, "head": {"ref": "shelf/work-abc123"}}}
    assert post_hook(app, "pull_request", payload) == 202
    assert app.runner.closed == [(WorkId("work-abc123"), True)]


def test_a_command_in_a_comment_reaches_the_work_as_a_decision() -> None:
    app = Fixture()
    app.runner.views[WorkId("work-abc123")] = WorkView(
        WorkId("work-abc123"), REPO, "alice", EntryPoint.NEED, Phase.SPEC_APPROVAL, waiting_for=Reason.GATE
    )
    payload: dict[str, object] = {
        "action": "created",
        "issue": {"pull_request": {}, "body": "<!-- shelf:work-abc123 -->\nneed"},
        "comment": {"body": "/shelf approve", "user": {"login": "carol"}, "author_association": "MEMBER"},
    }
    assert post_hook(app, "issue_comment", payload) == 202
    assert app.runner.decisions == [(WorkId("work-abc123"), PersonDecided("carol", DecisionKind.APPROVE))]


def test_an_event_we_do_not_act_on_is_acknowledged(app: Fixture) -> None:
    assert post_hook(app, "star", {"action": "created"}) == 202


def test_after_installing_the_app_github_sends_people_to_the_board(app: Fixture) -> None:
    response = app.client.get("/setup/installed", params={"installation_id": "1", "setup_action": "install"})
    assert (response.status_code, response.headers["location"]) == (303, "/board")


def test_the_health_check_answers(app: Fixture) -> None:
    assert app.client.get("/healthz").json() == {"status": "ok", "revision": "abc1234"}


def test_an_administrator_sees_the_work_of_every_repository_and_a_link_into_temporal() -> None:
    other = RepoRef("acme", "secret")
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.runner.views[WorkId("work-9")] = WorkView(WorkId("work-9"), other, "x", EntryPoint.NEED, Phase.INTAKE)
    fixture.sign_in()
    assert "acme/secret" in fixture.client.get("/board").text
    page = fixture.client.get("/work/work-9")
    assert page.status_code == 200
    assert "/namespaces/default/workflows/work-9" in page.text


def test_an_ordinary_person_sees_neither_other_repositories_nor_the_temporal_link(app: Fixture) -> None:
    other = RepoRef("acme", "secret")
    app.runner.views[WorkId("work-9")] = WorkView(WorkId("work-9"), other, "x", EntryPoint.NEED, Phase.INTAKE)
    app.runner.views[WorkId("work-1")] = WorkView(WorkId("work-1"), REPO, "alice", EntryPoint.NEED, Phase.INTAKE)
    app.sign_in()
    assert "acme/secret" not in app.client.get("/board").text
    assert app.client.get("/work/work-9").status_code == 404
    assert "workflows/work-1" not in app.client.get("/work/work-1").text


def test_the_board_and_the_start_page_warn_when_no_model_credential_is_set() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})), settings=replace(SETTINGS, model_configured=False))
    fixture.sign_in()
    for path in ("/board", "/start"):
        page = fixture.client.get(path).text
        assert "No model credential is set" in page
        assert "claude setup-token" in page


def test_an_ordinary_person_is_told_to_ask_the_administrator_when_no_credential_is_set() -> None:
    fixture = Fixture(settings=replace(SETTINGS, model_configured=False))
    fixture.sign_in()
    page = fixture.client.get("/board").text
    assert "Ask the administrator" in page
    assert "claude setup-token" not in page


def test_no_warning_is_shown_when_a_model_credential_is_set(app: Fixture) -> None:
    app.sign_in()
    assert "No model credential" not in app.client.get("/board").text
