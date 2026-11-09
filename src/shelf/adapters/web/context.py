"""What every router shares: the instance's wiring, templates, and the signed cookies that carry a session."""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache
from importlib import resources
from pathlib import Path

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from shelf.adapters.web import views
from shelf.adapters.web.sessions import Session, SessionStore
from shelf.adapters.web.webhook_log import WebhookLog
from shelf.domain.access import AccessRules, is_admin
from shelf.domain.model import WorkId, WorkView
from shelf.domain.polling import Mode
from shelf.ports.app_inspector import AppInspector
from shelf.ports.configs import RepoConfigs
from shelf.ports.context_sources import ContextSources
from shelf.ports.conversation import Conversations
from shelf.ports.documents import Documents
from shelf.ports.forge import Forge
from shelf.ports.references import References
from shelf.ports.runner import WorkRunner

SESSION_COOKIE = "shelf_session"
STATE_COOKIE = "shelf_oauth_state"
SESSION_SECONDS = 8 * 3600
STATE_SECONDS = 600
ASSETS = Path(str(resources.files("shelf.adapters.web")))


@dataclass(frozen=True, slots=True)
class WebSettings:
    """What the web application needs to know about the instance."""

    public_url: str
    app_slug: str
    client_id: str
    webhook_secret: str
    secret_key: str
    mode: Mode = Mode.LOCAL
    revision: str = "unknown"
    """The git revision this build came from, reported by the health check."""
    temporal_upstream: str = ""
    """Where Temporal's own interface listens, for the administrators' proxy; empty turns the proxy off."""
    temporal_writable: bool = False
    """Whether the proxy lets administrators change workflows (signal, terminate). Reading and queries always pass."""
    temporal_namespace: str = "default"
    model_configured: bool = True
    """False when no model credential is set: the interface then warns that agents will fail."""

    @property
    def secure(self) -> bool:
        """Cookies are marked Secure when the instance is served over HTTPS."""
        return self.public_url.startswith("https://")

    @property
    def install_url(self) -> str:
        """Where a person installs the App on their repositories."""
        return f"https://github.com/apps/{self.app_slug}/installations/new"


@dataclass(frozen=True, slots=True)
class WebDeps:
    """Everything the application is built from. Wired once, in the composition root."""

    settings: WebSettings
    rules: AccessRules
    forge: Forge
    runner: WorkRunner
    configs: RepoConfigs
    sessions: SessionStore
    temporal_transport: httpx.AsyncBaseTransport | None = None
    """For tests: how the proxy reaches Temporal's interface."""
    documents: Documents | None = None
    """Where the work's documents are read from; the interface shows none without it."""
    inspector: AppInspector | None = None
    """How the GitHub App is looked at, for the administrator's check; the page shows none without it."""
    references: References | None = None
    """Where existing material (an issue, a pull request, a file) is read from to start work; none without it."""
    context_sources: ContextSources | None = None
    """Where other repositories are read from to check what a person asks to be read; none without it."""
    conversations: Conversations | None = None
    """Where the pull request's conversation is read from; the page shows none without it."""


@cache
def asset(name: str) -> str:
    """The address of a static file with a fingerprint of its content.

    A browser never keeps an old copy of a file that changed, because its address changes with it.
    """
    digest = hashlib.sha1((ASSETS / "static" / name).read_bytes(), usedforsecurity=False).hexdigest()[:10]
    return f"/static/{name}?v={digest}"


def make_templates() -> Jinja2Templates:
    """The page templates, with the ``asset`` function for static files."""
    templates = Jinja2Templates(directory=ASSETS / "templates")
    templates.env.globals["asset"] = asset  # pyright: ignore[reportUnknownMemberType]
    return templates


@dataclass(frozen=True, slots=True)
class Web:
    """The shared toolbox of the routers."""

    deps: WebDeps
    webhooks: WebhookLog = field(default_factory=WebhookLog)
    templates: Jinja2Templates = field(default_factory=make_templates)

    @property
    def _signer(self) -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(self.deps.settings.secret_key, salt="shelf-cookie")

    def render(self, request: Request, name: str, session: Session | None, **context: object) -> HTMLResponse:
        """Render a template with what every page needs (who is signed in, the mode)."""
        base = {
            "user": session.identity.login if session else None,
            "mode": self.deps.settings.mode.value,
            "admin": self.is_admin(session),
            "webhook": self.webhook_status() if self.is_admin(session) else None,
            "model_ready": self.deps.settings.model_configured,
        }
        return self.templates.TemplateResponse(request, name, {**base, **context})

    def set_cookie(self, response: Response, name: str, value: str, max_age: int) -> None:
        """Set a signed, HttpOnly, SameSite=Lax cookie."""
        response.set_cookie(
            name,
            self._signer.dumps(value),
            max_age=max_age,
            httponly=True,
            samesite="lax",
            secure=self.deps.settings.secure,
        )

    def read_cookie(self, request: Request, name: str, max_age: int) -> str | None:
        """The value of a signed cookie, or ``None`` if absent, forged or too old."""
        raw = request.cookies.get(name)
        if raw is None:
            return None
        try:
            return str(self._signer.loads(raw, max_age=max_age))
        except BadSignature:
            return None

    def webhook_status(self) -> views.WebhookStatus:
        """What an administrator is told about the GitHub webhook."""
        return views.webhook_status(self.webhooks.last(), datetime.now(UTC))

    def is_admin(self, session: Session | None) -> bool:
        """Whether the signed-in person administers this instance."""
        return session is not None and is_admin(self.deps.rules, session.identity.login)

    async def visible_work(self, session: Session, work_id: str) -> WorkView:
        """The work, if this person may see it (its repository is visible to them, or they administer the instance)."""
        deps = self.deps
        work = await deps.runner.view(WorkId(work_id))
        repositories = {r.full_name for r in await deps.forge.repositories(session.user_token)}
        if work is None or (work.repo.full_name not in repositories and not self.is_admin(session)):
            raise HTTPException(status_code=404, detail="no such work")
        return work

    def temporal_link(self, work_id: str) -> str:
        """The address of a piece of work in Temporal's interface, or an empty string when the proxy is off."""
        settings = self.deps.settings
        if not settings.temporal_upstream:
            return ""
        return f"/temporal/namespaces/{settings.temporal_namespace}/workflows/{work_id}"

    def current(self, request: Request) -> Session | None:
        """The signed-in person, if any."""
        return self.deps.sessions.get(self.read_cookie(request, SESSION_COOKIE, SESSION_SECONDS))

    def signed_in(self, request: Request) -> Session:
        """A dependency: the session, or a redirect to the sign-in page."""
        session = self.current(request)
        if session is None:
            raise HTTPException(status_code=303, headers={"Location": "/"})
        return session

    def same_origin(self, request: Request) -> None:
        """A dependency for state-changing routes: refuse a request that comes from another origin."""
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") != self.deps.settings.public_url.rstrip("/"):
            raise HTTPException(status_code=403, detail="cross-origin request refused")
