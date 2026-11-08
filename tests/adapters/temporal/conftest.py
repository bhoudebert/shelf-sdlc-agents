"""A real Temporal dev server for the workflow tests.

It supports everything the board needs (listing workflows included). temporalio downloads it on first use; where that
binary cannot run (NixOS), set ``SHELF_TEMPORAL_DEV_SERVER`` to a ``temporal`` CLI. The tests use short real timers.
"""

import os
from collections.abc import AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    environment = await WorkflowEnvironment.start_local(  # pyright: ignore[reportUnknownMemberType]
        dev_server_existing_path=os.environ.get("SHELF_TEMPORAL_DEV_SERVER")
    )
    async with environment:
        yield environment
