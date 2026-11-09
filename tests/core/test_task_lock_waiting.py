"""锁等待的运行状态、占用者日志与 WS 推送。"""

import asyncio
from unittest.mock import patch

import pytest

from app.core import Publisher
from app.core.notify.lifecycle import NotificationTaskBase
from app.core.ws import protocol
from app.models.task import TaskMode
from app.task.mode_worker import AutoProxyWorker
from app.task.user_expander import UserExpander
from tests.core.test_task_tree_dispatch import Builtin
from tests.core.test_task_tree_dispatch import scheduler as scheduler


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_script_wait_logs_actual_holder_once_and_runs_only_in_child(
    scheduler, legacy
):
    manager, scripts, _, sid = scheduler
    entered, release, retried = asyncio.Event(), asyncio.Event(), asyncio.Event()
    holder = None
    messages = []
    retries = 0
    describe = manager.describe_lock_holders

    def describe_holders(config, *, cascade):
        nonlocal retries
        retries += 1
        if retries >= 2:
            retried.set()
        return describe(config, cascade=cascade)

    async def send(**message):
        messages.append(message)
        return True

    async def body_started(script):
        nonlocal holder
        assert script.status == "运行"
        if holder is None:
            holder = script.task_info.uid
            entered.set()
        if script.task_info.uid == holder:
            await release.wait()

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            await body_started(self.script_info)
            assert self.user_info.status == "运行"
            await self.user_info.set_state(status="完成")

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    class Body(Builtin):
        async def main_task(self):
            await body_started(self.script_info)
            await super().main_task()

    class Legacy(NotificationTaskBase):
        def __init__(self, script):
            super().__init__()
            self.script_info = script
            self.task_info = script.task_info

        async def main_task(self):
            ticket = await self.lock_script_config(scripts[sid])
            self.config_locks[sid] = ticket
            try:
                await self.spawn(Body(self.script_info))
            finally:
                self.config_locks.pop(sid)
                await scripts[sid].unlock(ticket)

        async def final_task(self):
            pass

        async def on_crash(self, error):
            await self.script_info.set_state(status="异常")

    if legacy:
        manager.manager_factories = {type(scripts[sid]): Legacy}
    else:
        manager.plugin_expander = lambda script, config: Expander(script, config)
    tree = {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}}
    with (
        patch.object(Publisher, "send", send),
        patch.object(manager, "describe_lock_holders", describe_holders),
    ):
        first = await manager.start(TaskMode.AUTO_PROXY, tree)
        first_run = manager.task_handler[first]
        await asyncio.wait_for(entered.wait(), 3)
        holder_description = describe(scripts[sid], cascade=True)
        assert (
            str(first) in holder_description and "占用者未知" not in holder_description
        )
        second = await manager.start(TaskMode.AUTO_PROXY, tree)
        second_run = manager.task_handler[second]
        try:
            await asyncio.wait_for(retried.wait(), 3)
            script = second_run.task_info.script_list[0]
            assert script.status == "等待"
            assert script.log.count("等待托管配置") == 1
            assert str(first) in script.log
            assert "占用者未知" not in script.log
            assert any(
                str(message["id"]) == str(second)
                and message["type"] == protocol.TASK_LOG_UPDATED
                and str(first) in message["data"].log
                for message in messages
            )
            states = [
                next(iter(message["data"]["scripts"]["data"].values()))["info"][
                    "status"
                ]
                for message in messages
                if str(message["id"]) == str(second)
                and message["type"] == protocol.TASK_INFO_UPDATED
            ]
            assert states and "运行" not in states
        finally:
            release.set()
        await asyncio.wait_for(first_run.accomplish.wait(), 3)
        await asyncio.wait_for(second_run.accomplish.wait(), 3)
    assert first_run.task_info.status == second_run.task_info.status == "success"
    assert not scripts[sid].is_locked


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_wait", [False, True])
async def test_user_wait_selects_current_node_logs_unknown_holder_and_can_stop(
    scheduler, cancel_wait
):
    manager, scripts, _, sid = scheduler
    config = next(iter(scripts[sid].UserData.values()))
    ticket = await config.lock_s()
    entered = asyncio.Event()
    waiting = asyncio.Event()

    async def send(**message):
        if (
            message["type"] == protocol.TASK_LOG_UPDATED
            and "等待用户配置" in message["data"].log
        ):
            waiting.set()
        return True

    class Worker(AutoProxyWorker):
        async def main_logic(self):
            assert self.user_info.status == "运行"
            entered.set()
            await asyncio.Event().wait()

    class Expander(UserExpander):
        def build_worker(self, user, config):
            return Worker(self, user, config)

    manager.plugin_expander = lambda script, entry: Expander(script, entry)
    with patch.object(Publisher, "send", send):
        uid = await manager.start(
            TaskMode.AUTO_PROXY,
            {0: {"uid": "-", "children": {0: {"uid": str(sid)}}}},
        )
        run = manager.task_handler[uid]
        try:
            await asyncio.wait_for(waiting.wait(), 3)
            script = run.task_info.script_list[0]
            user = script.user_list[0]
            assert script.status == "运行" and user.status == "等待"
            assert script.current.index == user.uid
            assert "占用者未知" in script.log
            assert str(uid) not in script.log
            if not cancel_wait:
                await config.unlock(ticket)
                ticket = None
                await asyncio.wait_for(entered.wait(), 3)
                assert user.status == "运行"
            await asyncio.wait_for(run.stop(), 3)
            assert run.task_info.status == "cancelled"
            assert entered.is_set() is not cancel_wait
        finally:
            if ticket is not None:
                await config.unlock(ticket)
    assert not scripts[sid].is_locked and not config.is_locked
