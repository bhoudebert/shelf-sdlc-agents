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
from shelf.domain.app_check import REQUIRED_EVENTS, REQUIRED_PERMISSIONS, AppFacts
from shelf.domain.config import RepoConfig, Role
from shelf.domain.model import Identity, RepoRef, WorkId, WorkView
from shelf.domain.pipeline import EntryPoint, Phase
from shelf.domain.result import Err, Ok, Result
from shelf.domain.work import DecisionKind, PersonDecided, Reason
from shelf.ports.app_inspector import AppInspector
from shelf.ports.documents import Documents
from shelf.ports.runner import UnreachableWorkError
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
    def __init__(  # noqa: PLR0913, PLR0917 - a test fixture with one knob per dependency
        self,
        rules: AccessRules | None = None,
        configs: FakeConfigs | None = None,
        settings: WebSettings = SETTINGS,
        transport: httpx.MockTransport | None = None,
        documents: Documents | None = None,
        inspector: AppInspector | None = None,
    ) -> None:
        self.forge = FakeForge(identities={"token-code": ALICE}, repos={"token-code": (REPO,)})
        self.runner = FakeRunner()
        deps = WebDeps(
            settings,
            rules or AccessRules(users=frozenset({"alice"})),
            self.forge,
            self.runner,
            configs or FakeConfigs(),
            SessionStore(),
            transport,
            documents,
            inspector,
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


def test_a_decision_on_work_the_engine_cannot_take_is_explained_not_a_server_error(app: Fixture) -> None:
    waiting(app)

    async def refuse(work_id: WorkId, decision: PersonDecided) -> None:
        raise UnreachableWorkError(work_id)

    app.runner.decide = refuse  # type: ignore[method-assign]
    response = app.client.post("/work/work-1/decide", data={"kind": "abort", "note": ""})
    assert response.status_code == 409
    assert "An administrator can close it" in response.text


def test_an_administrator_closes_work_that_cannot_be_steered() -> None:
    app = Fixture(AccessRules(admins=frozenset({"alice"})))
    waiting(app)
    assert "Close this work" in app.client.get("/work/work-1").text
    response = app.client.post("/work/work-1/close", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/board")
    assert [work_id for work_id, _ in app.runner.terminated] == [WorkId("work-1")]


def test_someone_who_is_not_an_administrator_cannot_close_work(app: Fixture) -> None:
    waiting(app)
    assert "Close this work" not in app.client.get("/work/work-1").text
    assert app.client.post("/work/work-1/close").status_code == 403
    assert app.runner.terminated == []


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
    app = Fixture(AccessRules(users=frozenset({"carol"})))
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
    assert app.client.get("/healthz").json() == {"status": "ok", "revision": "abc1234", "webhook": "none yet"}


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


class FakeDocuments:
    def __init__(self, found: dict[str, str], *, fail: bool = False) -> None:
        self.found, self.fail = found, fail

    async def read(self, repo: RepoRef, work_id: WorkId) -> dict[str, str]:
        if self.fail:
            message = "github down"
            raise RuntimeError(message)
        return self.found


def with_work(documents: Documents, phase: Phase = Phase.SPEC_APPROVAL) -> Fixture:
    fixture = Fixture(documents=documents)
    fixture.sign_in()
    fixture.runner.views[WorkId("work-1")] = WorkView(WorkId("work-1"), REPO, "alice", EntryPoint.NEED, phase)
    return fixture


def test_the_work_page_loads_its_documents_lazily() -> None:
    page = with_work(FakeDocuments({})).client.get("/work/work-1").text
    assert 'hx-get="/work/work-1/documents"' in page
    assert 'hx-trigger="load, every 20s"' in page


def test_the_documents_are_shown_rendered_with_the_current_one_open() -> None:
    fixture = with_work(FakeDocuments({"request.md": "loyalty", "spec.md": "# Loyalty spec\n\n- earn points"}))
    html = fixture.client.get("/work/work-1/documents").text
    assert "<h1>Loyalty spec</h1>" in html
    assert "<li>earn points</li>" in html
    assert 'class="doc" open' in html
    assert html.count("<details") == 2


def test_hostile_document_content_is_shown_as_text_not_run() -> None:
    fixture = with_work(FakeDocuments({"spec.md": "<script>alert(1)</script>"}))
    html = fixture.client.get("/work/work-1/documents").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_a_page_with_no_documents_yet_says_so() -> None:
    assert "Nothing is written yet" in with_work(FakeDocuments({})).client.get("/work/work-1/documents").text


def test_a_github_failure_is_reported_on_the_page_not_as_an_error() -> None:
    response = with_work(FakeDocuments({}, fail=True)).client.get("/work/work-1/documents")
    assert response.status_code == 200
    assert "could not be loaded" in response.text


def test_documents_of_work_on_a_repository_the_person_cannot_open_are_not_shown() -> None:
    fixture = with_work(FakeDocuments({"spec.md": "secret"}))
    fixture.runner.views[WorkId("work-9")] = WorkView(
        WorkId("work-9"), RepoRef("acme", "secret"), "x", EntryPoint.NEED, Phase.INTAKE
    )
    assert fixture.client.get("/work/work-9/documents").status_code == 404


def test_a_refresh_with_nothing_new_leaves_the_page_alone() -> None:
    fixture = with_work(FakeDocuments({"spec.md": "# S"}))
    panel = fixture.client.get("/work/work-1/panel")
    assert panel.status_code == 200
    version = panel.text.split("/panel?v=")[1].split('"')[0]
    assert fixture.client.get(f"/work/work-1/panel?v={version}").status_code == 204
    assert fixture.client.get("/work/work-1/panel?v=stale").status_code == 200


def test_the_panel_changes_its_fingerprint_when_the_work_moves_on() -> None:
    fixture = with_work(FakeDocuments({}))
    first = fixture.client.get("/work/work-1/panel").text.split("/panel?v=")[1].split('"')[0]
    fixture.runner.views[WorkId("work-1")] = WorkView(WorkId("work-1"), REPO, "alice", EntryPoint.NEED, Phase.DESIGN)
    assert fixture.client.get(f"/work/work-1/panel?v={first}").status_code == 200


def test_the_documents_refresh_the_same_way() -> None:
    fixture = with_work(FakeDocuments({"spec.md": "# S"}))
    html = fixture.client.get("/work/work-1/documents").text
    version = html.split("/documents?v=")[1].split('"')[0]
    assert fixture.client.get(f"/work/work-1/documents?v={version}").status_code == 204
    fixture.runner.views[WorkId("work-1")] = WorkView(WorkId("work-1"), REPO, "alice", EntryPoint.NEED, Phase.DESIGN)
    assert fixture.client.get(f"/work/work-1/documents?v={version}").status_code == 200


def test_a_decision_answer_carries_the_fingerprint_so_the_next_refresh_can_stay_quiet() -> None:
    fixture = with_work(FakeDocuments({}))
    answer = fixture.client.post("/work/work-1/decide", data={"kind": "approve"}).text
    assert "/panel?v=" in answer


def test_a_webhook_that_arrives_is_remembered_and_shown_to_administrators() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.sign_in()
    assert "No GitHub webhook has reached this instance" in fixture.client.get("/board").text
    assert post_hook(fixture, "star", {"action": "created"}) == 202
    board = fixture.client.get("/board").text
    assert "GitHub webhooks arrive" in board
    assert "No GitHub webhook has reached" not in board
    assert fixture.client.get("/healthz").json()["webhook"] == "star:ignored"


def test_a_webhook_with_the_wrong_secret_is_reported_with_what_to_do() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.sign_in()
    assert post_hook(fixture, "issue_comment", {}, lambda body: signed(body, "another")) == 401
    board = fixture.client.get("/board").text
    assert "does not match GITHUB_WEBHOOK_SECRET" in board
    assert fixture.client.get("/healthz").json()["webhook"] == "issue_comment:bad_signature"


def test_a_command_that_could_not_be_applied_is_reported_not_swallowed() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"}), users=frozenset({"carol"})))
    fixture.sign_in()
    payload: dict[str, object] = {
        "action": "created",
        "issue": {"pull_request": {}, "body": "<!-- shelf:work-abc123 -->\nneed"},
        "comment": {"body": "/shelf approve", "user": {"login": "carol"}, "author_association": "MEMBER"},
    }
    assert post_hook(fixture, "issue_comment", payload) == 202  # the work is unknown to this instance
    board = fixture.client.get("/board").text
    assert "was not applied" in board
    assert "work-abc123" in board


def test_a_command_from_someone_not_on_the_access_list_is_ignored() -> None:
    app = Fixture(AccessRules(users=frozenset({"alice"})))
    app.runner.views[WorkId("work-abc123")] = WorkView(
        WorkId("work-abc123"), REPO, "alice", EntryPoint.NEED, Phase.SPEC_APPROVAL, waiting_for=Reason.GATE
    )
    payload: dict[str, object] = {
        "action": "created",
        "issue": {"pull_request": {}, "body": "<!-- shelf:work-abc123 -->\nneed"},
        "comment": {"body": "/shelf approve", "user": {"login": "mallory"}, "author_association": "MEMBER"},
        "repository": {"owner": {"login": "stranger"}},
    }
    assert post_hook(app, "issue_comment", payload) == 202
    assert app.runner.decisions == []


class FakeInspector:
    def __init__(self, result: Result[AppFacts, str]) -> None:
        self.result = result

    async def facts(self) -> Result[AppFacts, str]:
        return self.result


def test_the_admin_page_tells_what_is_wrong_with_the_app_on_github() -> None:
    nothing = AppFacts(
        frozenset(), dict(REQUIRED_PERMISSIONS), "https://elsewhere.example/hook", webhook_secret_set=True
    )
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})), inspector=FakeInspector(Ok(nothing)))
    fixture.sign_in()
    page = fixture.client.get("/admin").text
    assert "GitHub App check" in page
    assert "not subscribed to: pull_request, issue_comment" in page
    assert "Subscribe to events" in page


def test_the_admin_page_says_when_the_app_could_not_be_checked() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})), inspector=FakeInspector(Err("GitHub refused it")))
    fixture.sign_in()
    page = fixture.client.get("/admin").text
    assert "could not be checked" in page
    assert "GitHub refused it" in page


def test_a_healthy_app_shows_only_green_findings() -> None:
    good = AppFacts(
        frozenset(REQUIRED_EVENTS),
        dict(REQUIRED_PERMISSIONS),
        "https://shelf.example.org/api/github/webhook",
        webhook_secret_set=True,
    )
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})), inspector=FakeInspector(Ok(good)))
    fixture.sign_in()
    page = fixture.client.get("/admin").text
    assert "finding-error" not in page
    assert "subscribed to the events it needs" in page


def test_ordinary_people_are_not_shown_the_webhook_status(app: Fixture) -> None:
    app.sign_in()
    assert "GitHub webhook." not in app.client.get("/board").text


def test_the_admin_page_lists_every_webhook_delivery_newest_first_with_what_became_of_it() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.sign_in()
    post_hook(fixture, "star", {"action": "created", "repository": {"full_name": "acme/shop"}})
    post_hook(fixture, "issue_comment", {}, lambda body: signed(body, "another"))
    page = fixture.client.get("/admin").text
    assert page.index("<code>issue_comment</code>") < page.index("<code>star</code>")  # newest first
    assert "REFUSED: wrong signature" in page
    assert "acme/shop" in page
    assert "not for us" in page


def test_the_admin_page_shows_the_instance_facts_and_never_a_secret() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"}), users=frozenset({"bob"})))
    fixture.sign_in()
    page = fixture.client.get("/admin").text
    assert "abc1234" in page  # the revision
    assert "/api/github/webhook" in page  # where GitHub should deliver
    assert "bob" in page
    assert "hook-secret" not in page
    assert "k" * 32 not in page


def test_an_empty_admin_page_says_what_to_check() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.sign_in()
    page = fixture.client.get("/admin").text
    assert "Nothing yet" in page
    assert "Recent deliveries" in page


def test_only_administrators_open_the_admin_page_and_see_its_link(app: Fixture) -> None:
    app.sign_in()
    assert app.client.get("/admin").status_code == 403
    assert 'href="/admin"' not in app.client.get("/board").text


def test_an_administrator_sees_the_admin_link_in_the_navigation() -> None:
    fixture = Fixture(AccessRules(admins=frozenset({"alice"})))
    fixture.sign_in()
    assert 'href="/admin"' in fixture.client.get("/board").text


def test_a_visitor_who_is_not_signed_in_is_sent_to_sign_in_from_the_admin_page(app: Fixture) -> None:
    assert app.client.get("/admin").status_code == 303


def test_a_row_of_the_board_says_what_the_work_is_and_links_its_pull_request(app: Fixture) -> None:
    app.sign_in()
    app.runner.views[WorkId("work-1")] = WorkView(
        WorkId("work-1"),
        REPO,
        "alice",
        EntryPoint.NEED,
        Phase.IMPLEMENT,
        pull_request_url="https://github.com/acme/shop/pull/12",
        title="Loyalty points at checkout",
    )
    page = app.client.get("/board").text
    assert "Loyalty points at checkout" in page
    assert "PR #12" in page
    assert 'href="https://github.com/acme/shop/pull/12"' in page
    assert "acme/shop" in page


def test_work_without_a_kept_title_is_still_listed_under_its_repository(app: Fixture) -> None:
    waiting(app)
    page = app.client.get("/board").text
    assert "acme/shop" in page
    assert "PR #" not in page
