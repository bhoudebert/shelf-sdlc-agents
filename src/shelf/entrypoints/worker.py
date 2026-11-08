"""The worker: runs the workflows and the activities (agents, git, GitHub). Scale it by running more."""

import asyncio
import logging
import os

import httpx
from temporalio.worker import Worker

from shelf.adapters.temporal.activities import build_activities
from shelf.adapters.temporal.workflow import WorkItemWorkflow
from shelf.domain.config import InvalidConfigError
from shelf.entrypoints import settings as settings_module
from shelf.entrypoints.wiring import build_services, connect

log = logging.getLogger("shelf.worker")


async def run() -> None:
    """Connect, wire, and serve the task queue until stopped."""
    settings = settings_module.from_environ(os.environ)
    if settings.github is None:
        log.warning(
            "No GitHub App is configured yet: register it from %s, put the credentials in the environment and "
            "restart. The worker is idle until then.",
            settings.public_url,
        )
        await asyncio.Event().wait()
        return
    temporal = await connect(settings)
    async with httpx.AsyncClient(timeout=30) as client:
        services = build_services(settings, settings.github, client, temporal)
        worker = Worker(
            temporal,
            task_queue=settings.task_queue,
            workflows=[WorkItemWorkflow],
            activities=build_activities(services.steps, services.pulls),
        )
        log.info("worker serving task queue %s", settings.task_queue)
        await worker.run()


def main() -> None:
    """Console entry point: ``shelf-worker``."""
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(run())
    except (settings_module.MissingSettingError, InvalidConfigError) as error:
        settings_module.exit_with(error)


if __name__ == "__main__":
    main()
