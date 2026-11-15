"""The guard on the admin page: what it has seen, and the rules an administrator adds from there."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, Response

from shelf.adapters.web.context import Web
from shelf.adapters.web.sessions import Session
from shelf.domain.guard import GuardReport
from shelf.domain.guard_rules import OverlayRule, allow_command, allow_file, allow_site, deny_host
from shelf.domain.result import Err


@dataclass(frozen=True, slots=True)
class GuardView:
    """The Guard section: the report, or the sentence that says why there is none."""

    report: GuardReport | None
    why_not: str
    can_apply: bool = False
    """Whether this instance keeps the rules added from the page (the buttons are shown only then)."""
    rules: tuple[OverlayRule, ...] = ()
    """The rules added from the page, oldest first."""


async def guard_view(web: Web) -> GuardView:
    """What the guard has seen, or why it cannot be shown. Never raises: the rest of the page must still load."""
    reader = web.deps.guard
    if reader is None:
        return GuardView(None, "The guard is not set up on this instance.")
    result = await reader.report()
    if isinstance(result, Err):
        return GuardView(None, f"Not available: {result.error}.")
    store = web.deps.guard_rules
    return GuardView(result.value, "", store is not None, await store.rules() if store else ())


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _back() -> Response:
    return RedirectResponse("/admin#guard-title", status_code=303)


def _may_allow(report: GuardReport, command: str) -> bool:
    """Whether ``command`` is one of the calls the page lists and that a rule can free."""
    return any(call.summary == command and call.kind == "bash" and call.can_be_allowed for call in report.recent)


def _refused(detail: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _administrator(web: Web, session: Session) -> str:
    """The login of an administrator; anybody else is refused."""
    if not web.is_admin(session):
        message = "administrators only"
        raise _refused(message, 403)
    return session.identity.login


async def _report_to_apply(web: Web) -> GuardReport:
    view = await guard_view(web)
    if view.report is None or not view.can_apply:
        message = "this instance cannot apply rules from the page"
        raise _refused(message, 409)
    return view.report


def _site_route(web: Web, routes: APIRouter) -> None:
    """The route that lets an administrator allow a site that agents' commands may reach."""

    @routes.post("/admin/guard/allow-site", dependencies=[Depends(web.same_origin)])
    async def allow_a_site(
        session: Annotated[Session, Depends(web.signed_in)], site: Annotated[str, Form()]
    ) -> Response:
        by = _administrator(web, session)
        store = web.deps.guard_rules
        if store is None:
            message = "this instance cannot apply rules from the page"
            raise _refused(message, 409)
        rule = allow_site(site, by, _now())
        if rule is None:
            message = "that is not a public host name (for example registry.example.org or *.example.org)"
            raise _refused(message)
        await store.add(rule)
        return _back()


def _file_route(web: Web, routes: APIRouter) -> None:
    """The route that lets an administrator free one of the project agent files for the agents' writes."""

    @routes.post("/admin/guard/allow-file", dependencies=[Depends(web.same_origin)])
    async def allow_a_file(
        session: Annotated[Session, Depends(web.signed_in)], pattern: Annotated[str, Form()]
    ) -> Response:
        by = _administrator(web, session)
        store = web.deps.guard_rules
        if store is None:
            message = "this instance cannot apply rules from the page"
            raise _refused(message, 409)
        rule = allow_file(pattern, by, _now())
        if rule is None:
            message = "that file is not one an administrator may free"
            raise _refused(message)
        await store.add(rule)
        return _back()


def router(web: Web) -> APIRouter:
    """The routes that change the guard's overlay: administrators only, and only for what the page lists."""
    routes = APIRouter()
    _site_route(web, routes)
    _file_route(web, routes)

    @routes.post("/admin/guard/allow", dependencies=[Depends(web.same_origin)])
    async def allow(session: Annotated[Session, Depends(web.signed_in)], command: Annotated[str, Form()]) -> Response:
        by = _administrator(web, session)
        report = await _report_to_apply(web)
        rule = allow_command(command, by, _now()) if _may_allow(report, command) else None
        if rule is None or web.deps.guard_rules is None:
            message = "that command is not among the calls the guard stopped"
            raise _refused(message)
        await web.deps.guard_rules.add(rule)
        return _back()

    @routes.post("/admin/guard/deny-host", dependencies=[Depends(web.same_origin)])
    async def deny(session: Annotated[Session, Depends(web.signed_in)], host: Annotated[str, Form()]) -> Response:
        by = _administrator(web, session)
        report = await _report_to_apply(web)
        rule = deny_host(host, by, _now()) if host.strip().lower() in report.web_hosts else None
        if rule is None or web.deps.guard_rules is None:
            message = "that host is not among the hosts the agents read"
            raise _refused(message)
        await web.deps.guard_rules.add(rule)
        return _back()

    @routes.post("/admin/guard/remove", dependencies=[Depends(web.same_origin)])
    async def remove(session: Annotated[Session, Depends(web.signed_in)], rule_id: Annotated[str, Form()]) -> Response:
        by = _administrator(web, session)
        store = web.deps.guard_rules
        if store is None:
            message = "this instance cannot apply rules from the page"
            raise _refused(message, 409)
        if not await store.remove(rule_id, by, _now()):
            message = "no such rule"
            raise _refused(message, 404)
        return _back()

    return routes
