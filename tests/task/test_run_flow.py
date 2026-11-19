import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.task.run_flow import RunPoint, observe_run


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "registered,mode", [(False, "CheckOnly"), (True, "Off"), (True, "CheckOnly")]
)
async def test_game_update_observed_only_when_flavor_checks(
    monkeypatch, registered, mode
):
    from app.task.MaaFW.tools.embedded import runner_task
    from app.utils.common.game_update import GameUpdateResult

    check = AsyncMock(
        return_value=GameUpdateResult(status="UpToDate", message="current")
    )
    monkeypatch.setattr(
        runner_task,
        "resolve_game_update_hook",
        lambda config: check if registered else None,
    )
    monkeypatch.setattr(runner_task, "resolve_host_adb", AsyncMock(return_value=None))
    worker = SimpleNamespace(
        script_config=SimpleNamespace(Run=SimpleNamespace(GameUpdateMode=mode)),
        run_plan=SimpleNamespace(resourceName="default"),
        _launched_package_name="test",
        _game_update_checked=False,
        _append_log=lambda text: None,
    )
    events = []
    with observe_run(lambda owner, event: events.append(event)):
        for _ in range(2):
            await runner_task.MaaFWPluginAutoProxyTask._ensure_game_updated(
                worker, "localhost", None
            )
    checked = registered and mode != "Off"
    assert check.await_count == int(checked)
    assert events == (
        [
            RunPoint("game_update", "entered"),
            RunPoint("game_update", "succeeded", "UpToDate"),
        ]
        if checked
        else []
    )


@pytest.mark.asyncio
async def test_retry_stays_with_its_attempt_and_never_crosses_parallel_runs():
    from app.task.run_flow import begin_attempt

    async def run(numbers):
        events = []
        with observe_run(
            lambda owner, event: events.append((event.stage, event.key, event.attempt))
        ):
            for phase, number in numbers:
                await asyncio.sleep(0)
                begin_attempt(numbers, number, phase=phase)
        return events

    retry, clean = await asyncio.gather(
        run([("daily", 1), ("daily", 2), ("weekly", 1)]), run([("", 1)])
    )
    assert retry == [
        ("attempt", "daily", 1),
        ("retry", "daily", 2),
        ("attempt", "daily", 2),
        ("attempt", "weekly", 1),
    ]
    assert clean == [("attempt", "", 1)]


@pytest.mark.asyncio
async def test_unmodified_plugin_can_stop_without_reporting_a_failure_or_retry():
    from auto_mas_core.adapters.script import AutoProxyWorker, observe_run

    from app.task.context import TaskContext
    from tests.support.scheduler import create_runtime_tree

    root, script, user = await create_runtime_tree(user_id="default")
    started = asyncio.Event()
    cleaned = asyncio.Event()

    class Plugin(AutoProxyWorker):
        async def main_logic(self):
            started.set()
            await asyncio.Event().wait()

        async def finish(self):
            cleaned.set()

    worker = Plugin(
        SimpleNamespace(task_info=root, script_info=script, context=TaskContext()),
        user,
        None,
    )
    events = []
    cancelled_view = asyncio.get_running_loop().create_future()
    cancelled_view.cancel()

    def closing_view(owner, event):
        events.append((owner, event))
        if event == RunPoint("finalize", "entered"):
            cancelled_view.result()

    with observe_run(closing_view):
        worker.start()
        await asyncio.wait_for(started.wait(), timeout=2)
        await worker.stop()
    assert cleaned.is_set() and user.status == "已取消"
    assert all(owner is worker for owner, _ in events)
    assert [event for _, event in events] == [
        RunPoint("run", "entered"),
        RunPoint("finalize", "entered"),
        RunPoint("finalize", "succeeded"),
        RunPoint("task", "cancelled"),
    ]


@pytest.mark.asyncio
async def test_plugin_without_a_result_fails_once_after_cleanup():
    from auto_mas_core.adapters.script import AutoProxyWorker

    from app.task.context import TaskContext
    from tests.support.scheduler import create_runtime_tree

    root, script, user = await create_runtime_tree(user_id="default")

    class NoResult(AutoProxyWorker):
        async def main_logic(self):
            pass

    async def record(user, *, status, reason):
        await user.set_state(status=status)

    worker = NoResult(
        SimpleNamespace(
            task_info=root,
            script_info=script,
            context=TaskContext(),
            record_user_state=record,
        ),
        user,
        None,
    )
    events = []
    with observe_run(lambda owner, event: events.append(event)):
        await worker.run()
    assert user.status == "异常"
    assert [e for e in events if e.stage == "task"] == [RunPoint("task", "failed")]
