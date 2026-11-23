from uuid import uuid4

import pytest
import pytest_asyncio

from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.task.MaaFW.tools.embedded.runner_task import MaaFWPluginAutoProxyTask
from app.task.run_flow import RunPoint, observe_run
from tests.support.scheduler import create_runtime_tree


@pytest_asyncio.fixture
async def worker():
    uid = uuid4()
    root, script, _ = await create_runtime_tree(
        script_id=str(uuid4()), user_id=str(uid)
    )
    return MaaFWPluginAutoProxyTask(
        script, MaaFWConfig(), {uid: MaaFWUserConfig()}, None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,category,counted,expected",
    [
        ("timeout", "task_timeout", True, "failed"),
        ("stopped", "script_stopped", True, "failed"),
        ("stopped", "script_stopped", False, "stopped"),
        ("stopped", "signal", True, "stopped"),
        ("stopped", "user_stopped", True, "cancelled"),
    ],
)
async def test_worker_result_shown_to_observers(
    worker, outcome, category, counted, expected
):
    worker._begin_run_record_attempt(1)
    seen = []
    with observe_run(lambda _, event: seen.append(event)):
        worker._on_run_record_event(
            dict(
                kind="task_end",
                name="daily",
                index=0,
                at=2,
                outcome=outcome,
                category=category,
                counted=counted,
            )
        )
    assert seen == [RunPoint("special", expected, "daily")]


@pytest.mark.asyncio
async def test_late_worker_message_does_not_restart_finished_task(worker):
    start = dict(kind="task_start", name="daily", index=0, total=1, at=1)
    worker._begin_run_record_attempt(1)
    seen = []
    with observe_run(lambda _, event: seen.append(event)):
        worker._on_run_record_event(start)
        worker._run_record.finish_attempt(outcome="failed")
        worker._on_run_record_event(start)
    assert seen == [RunPoint("special", "entered", "daily")]
