import asyncio
from types import SimpleNamespace

import pytest
from auto_mas_core.adapters.script import AutoProxyWorker, UserExpander, observe_run

from app.models.config import ScriptEntry
from app.task.context import TaskContext
from app.task.run_flow import RunPoint, begin_attempt
from tests.config_support import activate_config
from tests.support.scheduler import create_runtime_tree


@pytest.mark.asyncio
async def test_retry_stays_with_its_attempt_and_never_crosses_parallel_runs():
    async def run(phase, number):
        events = []
        with observe_run(lambda _, event: events.append(event)):
            await asyncio.sleep(0)
            begin_attempt(phase, number, phase=phase)
        return events

    retry, clean = await asyncio.gather(run("daily", 2), run("weekly", 1))
    assert retry == [
        RunPoint("retry", "entered", "daily", 2),
        RunPoint("attempt", "entered", "daily", 2),
    ]
    assert clean == [RunPoint("attempt", "entered", "weekly", 1)]


@pytest.mark.asyncio
async def test_cancelled_observer_does_not_prevent_plugin_cleanup():
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

    def closing_view(_, event):
        if event == RunPoint("finalize", "entered"):
            events.append("closing")
            raise asyncio.CancelledError
        if event.stage == "task":
            events.append(event.state)

    with observe_run(closing_view):
        worker.start()
        await asyncio.wait_for(started.wait(), timeout=2)
        await worker.stop()
    assert cleaned.is_set() and user.status == "已取消"
    assert events == ["closing", "cancelled"]


@pytest.mark.asyncio
async def test_plugin_without_a_result_reports_one_failure():
    root, script, user = await create_runtime_tree(user_id="default")

    class NoResult(AutoProxyWorker):
        async def main_logic(self):
            pass

    class Plugin(UserExpander):
        def build_worker(self, user, config):
            return NoResult(self, user, config)

    plugin = Plugin(script, await activate_config(ScriptEntry()))
    events = []
    with observe_run(lambda _, event: events.append(event)):
        await plugin.run()
    assert user.status == "异常"
    assert "未给出用户结果" in user.result
    assert [e for e in events if e.stage == "task"] == [RunPoint("task", "failed")]
