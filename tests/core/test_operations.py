"""通过真实配置及背景任务验证命令身份、终态、准入和 owner 暂停。"""

import asyncio
from uuid import uuid4

import pytest
from pydantic import Field, PrivateAttr

from app.config import ConfigEntry, ConfigGroup, Trigger
from app.config import trigger_field as config_trigger_field
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.plugin.operations import OperationDispatcher, OperationUnavailable
from app.plugin.config import PluginCommandEntry, trigger_field


class PlainConfig(ConfigEntry):
    class Action(ConfigGroup):
        run: Trigger = False

    action: Action = Field(default_factory=Action)
    _calls: int = PrivateAttr(default=0)

    @config_trigger_field("action.run")
    def run_command(self):
        """普通配置触发器同步执行，不依赖插件操作中心。"""
        self._calls += 1


class CommandConfig(PluginCommandEntry):
    class Action(ConfigGroup):
        run: Trigger = False
        fixed: Trigger = False

    action: Action = Field(default_factory=Action)
    _started: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)
    _release: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)
    _error: bool = PrivateAttr(default=False)
    _calls: int = PrivateAttr(default=0)

    @trigger_field("action.run")
    async def run_command(self):
        """记录触发器执行并等待测试放行，按测试设置决定是否抛出业务错误。"""
        self._calls += 1
        self._started.set()
        await self._release.wait()
        if self._error:
            raise ValueError("business failed")

    @trigger_field("action.fixed", cancellable=False)
    async def fixed_command(self):
        """复用相同业务行为，提供不允许取消的触发器测试入口。"""
        await self.run_command()


@pytest.mark.asyncio
async def test_duplicate_busy_failure_and_repeatable_result():
    """验证同一触发器去重、容量拒绝、失败记录以及完成结果可重复查询。"""
    background = BackgroundTaskRegistry()
    first, second = CommandConfig.build(), CommandConfig.build()
    await first.activate()
    await second.activate()
    nodes = {first.uid: first, second.uid: second}
    dispatcher = OperationDispatcher(
        resolve_node=nodes.get, resolve_owner=lambda _: None
    )
    dispatcher.initialize(max_running=1, background=background)
    try:
        uid = dispatcher.submit(first, group="action", field="run", value=True)
        assert dispatcher.submit(first, group="action", field="run", value=True) == uid
        with pytest.raises(OperationUnavailable, match="busy"):
            dispatcher.submit(second, group="action", field="run", value=True)
        await first._started.wait()
        first._error = True
        first._release.set()
        assert await background.get_group("operations").drain(2)
        assert first._calls == 1
        assert dispatcher.get(uid).state == "failed"
        assert dispatcher.get(uid).errorCode == "ValueError"
        assert dispatcher.get(uid).state == "failed"
    finally:
        await dispatcher.shutdown()


@pytest.mark.asyncio
async def test_prestart_cancel_and_non_cancellable_owner_pause():
    """验证开始前取消和插件暂停会正确等待不可取消操作，暂停期间拒绝新请求。"""
    background = BackgroundTaskRegistry()
    entry = CommandConfig.build()
    await entry.activate()
    owner = uuid4()
    dispatcher = OperationDispatcher(
        resolve_node=lambda uid: entry if uid == entry.uid else None,
        resolve_owner=lambda _: owner,
    )
    dispatcher.initialize(max_running=1, background=background)
    try:
        uid = dispatcher.submit(entry, group="action", field="run", value=True)
        assert (await dispatcher.cancel(uid)).state == "cancelled"
        assert entry._calls == 0
        uid = dispatcher.submit(entry, group="action", field="fixed", value=True)
        await entry._started.wait()
        with pytest.raises(OperationUnavailable, match="not_cancellable"):
            await dispatcher.cancel(uid)
        entered = asyncio.Event()

        async def pause():
            """进入插件暂停上下文并断言新增操作被拒绝，再通知测试已完成在途操作等待。"""
            async with dispatcher.pause_owners([owner]):
                entered.set()
                with pytest.raises(OperationUnavailable, match="owner_stopping"):
                    dispatcher.submit(entry, group="action", field="run", value=True)

        waiter = asyncio.create_task(pause())
        await asyncio.sleep(0)
        assert not entered.is_set()
        entry._release.set()
        await waiter
        assert dispatcher.get(uid).state == "succeeded"
    finally:
        await dispatcher.shutdown()


@pytest.mark.asyncio
async def test_plain_config_and_plugin_assignment_have_separate_dispatch(monkeypatch):
    """配置更新保持 None 返回值，普通 Trigger 直接执行，插件赋值和命令入口统一纳管。"""
    from app.core.plugin import operations

    background = BackgroundTaskRegistry()
    plain, plugin = PlainConfig.build(), CommandConfig.build()
    await plain.activate()
    await plugin.activate()
    nodes = {plain.uid: plain, plugin.uid: plugin}
    dispatcher = OperationDispatcher(
        resolve_node=nodes.get, resolve_owner=lambda _: None
    )
    dispatcher.initialize(max_running=2, background=background)
    monkeypatch.setattr(operations, "Operations", dispatcher)
    try:
        assert (
            await plain.update(PlainConfig.model_validate({"action": {"run": True}}))
            is None
        )
        assert plain._calls == 1
        assert dispatcher.list() == []
        with pytest.raises(OperationUnavailable, match="target_not_found"):
            await dispatcher.start(
                config_uid=plain.uid, group="action", field="run", value=True
            )

        assert (
            await plugin.update(CommandConfig.model_validate({"action": {"run": True}}))
            is None
        )
        plugin.action.run = True
        await plugin._started.wait()
        records = dispatcher.list(config_uid=plugin.uid)
        assert len(records) == 1
        assert plugin._calls == 1
        # 同一插件的另一个 Trigger 可以并发，不受同配置整体互斥限制。
        second = await dispatcher.start(
            config_uid=plugin.uid, group="action", field="fixed", value=True
        )
        plugin._release.set()
        assert await background.get_group("operations").drain(2)
        assert plugin._calls == 2
        assert dispatcher.get(second).state == "succeeded"
        assert dispatcher.get(records[0].operationId).state == "succeeded"
    finally:
        await dispatcher.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", ["cancel", "pause", "shutdown"])
async def test_operation_wait_includes_terminal_notification_attempt(waiting):
    """取消、插件停用和应用退出都等待结果通知尝试，通知失败不覆盖命令业务终态。"""
    background = BackgroundTaskRegistry()
    entry = CommandConfig.build()
    await entry.activate()
    owner = uuid4()
    published, release_notification = asyncio.Event(), asyncio.Event()

    async def publish(info):
        """阻塞通知以检查等待边界，再模拟 WS 通知失败。"""
        published.set()
        await release_notification.wait()
        raise RuntimeError("notification unavailable")

    dispatcher = OperationDispatcher(
        resolve_node=lambda uid: entry if uid == entry.uid else None,
        resolve_owner=lambda _: owner,
        publish=publish,
    )
    dispatcher.initialize(max_running=1, background=background)
    waiter = None
    try:
        uid = dispatcher.submit(entry, group="action", field="run", value=True)
        await entry._started.wait()

        async def pause():
            """模拟插件停用入口，进入暂停上下文前等待所属命令完整结束。"""
            async with dispatcher.pause_owners([owner]):
                pass

        waiter = asyncio.create_task(
            dispatcher.cancel(uid)
            if waiting == "cancel"
            else pause()
            if waiting == "pause"
            else dispatcher.shutdown()
        )
        await asyncio.wait_for(published.wait(), timeout=2)
        assert not waiter.done()
        assert dispatcher.get(uid).state == "cancelled"
        release_notification.set()
        await asyncio.wait_for(waiter, timeout=2)
        assert dispatcher.get(uid).state == "cancelled"
    finally:
        release_notification.set()
        if waiter is not None:
            await waiter
        await dispatcher.shutdown()
