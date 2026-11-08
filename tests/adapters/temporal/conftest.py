"""A real Temporal server for the workflow tests.

CI uses the time-skipping test server that temporalio downloads. Where that binary cannot run (NixOS), set
``SHELF_TEMPORAL_DEV_SERVER`` to a ``temporal`` CLI and the tests use its dev server: the tests use short real timers
so they pass on both.
"""

import os
from collections.abc import AsyncIterator

import pytest
from temporalio.testing import WorkflowEnvironment


@pytest.fixture
async def env() -> AsyncIterator[WorkflowEnvironment]:
    path = os.environ.get("SHELF_TEMPORAL_DEV_SERVER")
    if path:
        environment = await WorkflowEnvironment.start_local(  # pyright: ignore[reportUnknownMemberType]
            dev_server_existing_path=path
        )
    else:
        environment = await WorkflowEnvironment.start_time_skipping()
    async with environment:
        yield environment
