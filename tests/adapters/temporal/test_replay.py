"""Histories recorded by earlier releases must keep replaying: work already running survives every update.

``g1-*`` were recorded by the first release (protocol 1, before the pull request opened early); ``p2-*`` by protocol 2.
When a change to the workflow or to ``decide`` makes one of them fail, do not edit the fixture: gate the change on a new
protocol (see ``CURRENT_PROTOCOL``), so work started before it keeps its behaviour. To add a fixture for a new protocol,
run this module with ``SHELF_RECORD_HISTORIES=<name>`` set.
"""

import asyncio
import json
import os
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from shelf.adapters.temporal import wire
from shelf.adapters.temporal.workflow import WorkItemWorkflow
from shelf.domain.work import DecisionKind
from tests.adapters.temporal.test_workflow import FakePulls, FakeSteps, start, until, work_input, worker

HISTORIES = Path(__file__).parent / "histories"


@pytest.mark.parametrize("fixture", sorted(HISTORIES.glob("*.json")), ids=lambda path: path.stem)
async def test_a_history_recorded_by_an_earlier_release_still_replays(fixture: Path) -> None:
    recorded = await asyncio.to_thread(fixture.read_text)
    history = WorkflowHistory.from_json(f"recorded-{fixture.stem}", json.loads(recorded))
    await Replayer(workflows=[WorkItemWorkflow]).replay_workflow(history)


@pytest.mark.skipif(not os.environ.get("SHELF_RECORD_HISTORIES"), reason="only when recording fixtures")
async def test_record_histories(env: WorkflowEnvironment) -> None:
    name = os.environ["SHELF_RECORD_HISTORIES"]
    async with worker(env, FakeSteps(), FakePulls()):
        handle = await start(env, work_input("need"))
        await until(handle, lambda s: s.waiting_for == "gate")
        (HISTORIES / f"{name}-gate.json").write_text((await handle.fetch_history()).to_json())
        await handle.signal(WorkItemWorkflow.decided, wire.DecisionDto("carol", DecisionKind.APPROVE, ""))
        await until(handle, lambda s: s.waiting_for == "merge")
        (HISTORIES / f"{name}-merge.json").write_text((await handle.fetch_history()).to_json())
