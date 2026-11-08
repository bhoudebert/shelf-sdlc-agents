"""The administrator's page: what GitHub has sent, and the facts about this instance, so nobody has to guess."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response

from shelf.adapters.web import views
from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.app_check import Finding, Level, check_app
from shelf.domain.result import Err


def router(web: Web) -> APIRouter:
    """The admin route."""
    routes = APIRouter()

    async def app_findings() -> tuple[Finding, ...]:
        """What is wrong with the App's setup on GitHub, or why that could not be read. Empty without an inspector."""
        inspector = web.deps.inspector
        if inspector is None:
            return ()
        result = await inspector.facts()
        if isinstance(result, Err):
            return (Finding(Level.ERROR, "The App could not be checked.", result.error),)
        return check_app(result.value, f"{web.deps.settings.public_url.rstrip('/')}/api/github/webhook")

    @routes.get("/admin", response_class=HTMLResponse)
    async def admin(request: Request, session: Annotated[Session, Depends(web.signed_in)]) -> Response:
        if not web.is_admin(session):
            raise HTTPException(status_code=403, detail="administrators only")
        settings, rules = web.deps.settings, web.deps.rules
        facts = [
            ("Revision", settings.revision),
            ("Address", settings.public_url),
            ("Mode", settings.mode.value),
            ("GitHub App", settings.app_slug),
            ("Model credential", "set" if settings.model_configured else "NOT SET: agents will fail"),
            ("Temporal's interface", "served at /temporal" if settings.temporal_upstream else "not configured"),
            ("Administrators", ", ".join(sorted(rules.admins)) or "none"),
            ("Users allowed", ", ".join(sorted(rules.users)) or "anyone"),
            ("Organisations allowed", ", ".join(sorted(rules.organisations)) or "any"),
        ]
        return web.render(
            request,
            "admin.html",
            session,
            facts=facts,
            findings=await app_findings(),
            deliveries=views.delivery_rows(web.webhooks.newest_first()),
            app_url=f"https://github.com/apps/{settings.app_slug}",
        )

    return routes
