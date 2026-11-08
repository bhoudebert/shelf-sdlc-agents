"""The web service. With the GitHub App configured it serves the product; without it, the one-click registration."""

import asyncio
import logging
import os

import httpx
import uvicorn
from fastapi import FastAPI

from shelf.adapters.caching.forge import CachedForge
from shelf.adapters.web.app import create_app
from shelf.adapters.web.context import WebDeps, WebSettings
from shelf.adapters.web.sessions import SessionStore
from shelf.domain.config import InvalidConfigError
from shelf.entrypoints import settings as settings_module
from shelf.entrypoints.setup import create_setup_app
from shelf.entrypoints.wiring import build_services, connect

log = logging.getLogger("shelf.web")


async def build(settings: settings_module.Settings) -> FastAPI:
    """The product when the App is registered, the registration helper when it is not."""
    if settings.github is None:
        log.warning("GITHUB_APP_ID is not set: serving the one-click registration at %s", settings.public_url)
        return create_setup_app(settings.public_url, revision=settings.revision)
    client = httpx.AsyncClient(timeout=30)
    services = build_services(settings, settings.github, client, await connect(settings))
    github = settings.github
    web = WebSettings(
        public_url=settings.public_url,
        app_slug=github.slug,
        client_id=github.client_id,
        webhook_secret=github.webhook_secret,
        secret_key=settings.session_secret,
        mode=services.operator.mode,
        revision=settings.revision,
        temporal_upstream=settings.temporal_ui_upstream,
        temporal_writable=settings.temporal_ui_writable,
        temporal_namespace=settings.temporal_namespace,
        model_configured=settings.model_credential,
    )
    return create_app(
        WebDeps(
            web,
            services.operator.access,
            CachedForge(services.forge),
            services.runner,
            services.configs,
            SessionStore(),
        )
    )


async def serve(settings: settings_module.Settings) -> None:
    """Build the application and serve it, in one event loop (the Temporal client lives in it)."""
    app = await build(settings)
    config = uvicorn.Config(app, host="0.0.0.0", port=settings.port, log_level="info")  # noqa: S104 - in a container
    await uvicorn.Server(config).serve()


def main() -> None:
    """Console entry point: ``shelf-web``."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(serve(settings_module.from_environ(os.environ)))
    except (settings_module.MissingSettingError, InvalidConfigError) as error:
        settings_module.exit_with(error)


if __name__ == "__main__":
    main()
