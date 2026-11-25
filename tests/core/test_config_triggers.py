"""通过真实配置及背景任务验证命令身份、终态、准入和 owner 暂停。"""

import asyncio
from threading import Event
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from pydantic import Field, PrivateAttr

from app.config import (
    ConfigCollection,
    ConfigEntry,
    ConfigGroup,
    ExportContext,
    Trigger,
    config_manager,
    trigger,
    trigger_field,
)
from app.config.core.manager import ConfigManager, TriggerUnavailable
from app.core.background_tasks import BackgroundTaskRegistry
from app.plugin.errors import PluginBusyError
from app.plugin.types import PluginState
from tests.core.test_plugin_cascade import cascade_plugins as cascade_plugins


class PlainConfig(ConfigEntry):
    class Action(ConfigGroup):
        run: Trigger = trigger(timeout=0.05)

    action: Action = Field(default_factory=Action)
    _calls: int = PrivateAttr(default=0)
    _release: Event = PrivateAttr(default_factory=Event)
    _started: Event = PrivateAttr(default_factory=Event)

    @trigger_field("action.run")
    def run_command(self):
        self._calls += 1
        self._started.set()
        assert self._release.wait(2)


class CommandConfig(ConfigEntry):
    class Action(ConfigGroup):
        run: Trigger = None
        fixed: Trigger = None

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

    @trigger_field("action.fixed", finish_on_cancel=True)
    async def fixed_command(self):
        """复用相同业务行为，模拟取消后须等待结束的临界操作。"""
        await self.run_command()


@pytest.mark.asyncio
async def test_config_ui_reports_committed_nodes_and_trigger_transitions(monkeypatch):
    class Target(CommandConfig):
        class Info(ConfigGroup):
            name: str = "old"

        info: Info = Field(default_factory=Info)

    changes: list[frozenset[UUID]] = []
    monkeypatch.setattr(config_manager, "_ui_listener", changes.append)
    collection = ConfigCollection[Target].build([Target])
    await collection.activate()
    uid = collection.add(Target)
    await collection.commit()
    target = collection[uid]
    expected = frozenset((collection.uid, uid))
    changes.clear()

    with pytest.raises(ValueError, match="rollback"):
        async with config_manager.transaction():
            async with config_manager.transaction(new_boundary=True):
                target.info.name = "rolled back"
                await target.commit()
            assert changes == []
            raise ValueError("rollback")
    assert target.info.name == "old"
    assert changes == []

    async with config_manager.transaction():
        target.info.name = "committed"
        await target.commit()
        assert changes == []
    assert changes == [expected]
    target.info.name = "committed"
    await target.commit()
    assert changes == [expected]

    first = await target.lock_s(cascade=False)
    second = await target.lock_s(cascade=False)
    await target.unlock(first)
    assert changes == [expected, expected]
    await target.unlock(second)
    assert changes == [expected, expected, expected]

    background = BackgroundTaskRegistry()
    dispatcher = ConfigManager()
    dispatcher.bind_ui_listener(changes.append)
    dispatcher.initialize_triggers(background, max_running=1)
    monkeypatch.setattr("app.config.core.entry.config_manager", dispatcher)
    changes.clear()
    try:
        with pytest.raises(ValueError, match="rollback trigger"):
            async with dispatcher.transaction():
                target.action.run = True
                assert target.action.run is None
                raise ValueError("rollback trigger")
        assert changes == []
        assert target.action.run is None

        async with dispatcher.transaction():
            target.action.run = True
            assert target.action.run is None
            assert changes == []
        task = target.action.run
        assert task is not None
        assert target.action.run == task
        assert changes == [expected]
        await asyncio.wait_for(target._started.wait(), timeout=2)
        dispatcher.submit_trigger(target, group="action", field="run", value=False)
        assert target.action.run == task
        assert changes == [expected, expected]
        assert await background.get_group("config-triggers").drain(2)
        assert target.action.run is None
        assert changes == [expected, expected, expected]
    finally:
        target._release.set()
        await dispatcher.shutdown_triggers()
        await background.shutdown(timeout=2)


@pytest_asyncio.fixture
async def lifecycle_triggers(cascade_plugins, monkeypatch, tmp_path):
    """将真实插件和业务触发器接入同一配置管理器，隔离背景组并确保故障探针也能结束。"""
    from app.core import plugin
    from app.core.plugin import manager as plugin_module

    manager, records = await cascade_plugins({"lifecycle_probe": ()})
    record = records["lifecycle_probe"]
    await manager.enable(record)
    work = CommandConfig.build()
    await work.activate()
    background = BackgroundTaskRegistry()
    dispatcher = ConfigManager()
    dispatcher.register_root(record.root, tmp_path / "registry.yaml")
    dispatcher.register_root(work, tmp_path / "work.yaml")
    dispatcher.initialize_triggers(
        background, max_running=3, resolve_owner=lambda _: record.uid
    )
    monkeypatch.setattr(plugin, "Plugin", manager)
    monkeypatch.setattr(plugin_module, "config_manager", dispatcher)
    try:
        yield manager, record, work, dispatcher, background
    finally:
        work._release.set()
        await background.shutdown(timeout=2)
        await dispatcher.shutdown_triggers()
        if record.info.state == PluginState.ENABLED:
            await manager.disable(record)


@pytest.mark.asyncio
async def test_concurrent_lifecycle_commands_finish_without_waiting_for_each_other(
    lifecycle_triggers,
):
    """同一启用插件先受理禁用和重载，前者完成、后者报告忙，不能互相等待。"""
    _, record, _, dispatcher, background = lifecycle_triggers
    disable = dispatcher.write_trigger(
        config_uid=record.uid, group="info", field="disable", value=True
    )
    reload = dispatcher.write_trigger(
        config_uid=record.uid, group="info", field="reload", value=True
    )
    assert await background.get_group("config-triggers").drain(2)
    assert dispatcher.trigger_result(disable).state == "succeeded"
    assert dispatcher.trigger_result(reload).state == "failed"
    assert dispatcher.trigger_result(reload).error_code == "PluginBusyError"
    assert record.info.state == PluginState.DISABLED


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["disable", "reload", "unload", "uninstall"])
async def test_busy_lifecycle_leaves_running_work_and_service_available(
    lifecycle_triggers, action
):
    """其他生命周期占用互斥期间，被拒绝的操作不能取消业务触发器或关闭服务准入。"""
    manager, record, work, dispatcher, background = lifecycle_triggers
    operation = dispatcher.write_trigger(
        config_uid=work.uid, group="action", field="run", value=True
    )
    await work._started.wait()
    async with manager._hold():
        with pytest.raises(PluginBusyError):
            await getattr(manager, action)(record)
        assert dispatcher.trigger_result(operation).state == "running"
        assert record.info.state == PluginState.ENABLED
        assert await manager.services.require("lifecycle_probe")() is record._plugin
    work._release.set()
    assert await background.get_group("config-triggers").drain(2)
    assert dispatcher.trigger_result(operation).state == "succeeded"


@pytest.mark.asyncio
async def test_disable_gives_up_when_trigger_outlasts_drain_limit(
    lifecycle_triggers, monkeypatch
):
    """配置触发器一直不收尾：停用在同一上限内以「插件系统忙」拒绝，插件照常接单、触发器不受影响。"""
    from app.core.plugin import manager as plugin_module

    monkeypatch.setattr(plugin_module, "_PAUSE_DRAIN_TIMEOUT", 0.3)
    manager, record, work, dispatcher, background = lifecycle_triggers
    operation = dispatcher.write_trigger(
        config_uid=work.uid, group="action", field="fixed", value=True
    )
    await work._started.wait()
    plugin = record._plugin
    async with asyncio.timeout(5):
        with pytest.raises(PluginBusyError) as caught:
            await manager.disable(record)
    assert caught.value.message == "插件系统忙，请稍后重试"
    assert record.info.state == PluginState.ENABLED
    assert record._plugin is plugin
    assert await manager.services.require("lifecycle_probe")() is plugin
    assert dispatcher.trigger_result(operation).state == "running"
    # 暂停已撤回：这个插件的配置操作照常受理。
    second = CommandConfig.build()
    await second.activate()
    dispatcher.submit_trigger(second, group="action", field="run", value=True)
    second._release.set()
    work._release.set()
    assert await background.get_group("config-triggers").drain(2)
    assert dispatcher.trigger_result(operation).state == "succeeded"
    await manager.disable(record)
    assert record.info.state == PluginState.DISABLED


@pytest.mark.asyncio
async def test_duplicate_busy_failure_and_repeatable_result():
    """验证同一触发器去重、容量拒绝、失败记录以及完成结果可重复查询。"""
    background = BackgroundTaskRegistry()
    first, second = CommandConfig.build(), CommandConfig.build()
    await first.activate()
    await second.activate()
    dispatcher = ConfigManager()
    dispatcher.initialize_triggers(background, max_running=1)
    try:
        uid = dispatcher.submit_trigger(first, group="action", field="run", value=True)
        assert (
            dispatcher.submit_trigger(first, group="action", field="run", value=True)
            == uid
        )
        with pytest.raises(TriggerUnavailable, match="busy"):
            dispatcher.submit_trigger(second, group="action", field="run", value=True)
        await first._started.wait()
        first._error = True
        first._release.set()
        assert await background.get_group("config-triggers").drain(2)
        assert first._calls == 1
        assert dispatcher.trigger_result(uid).state == "failed"
        assert dispatcher.trigger_result(uid).error_code == "ValueError"
        assert dispatcher.trigger_result(uid).state == "failed"
    finally:
        await dispatcher.shutdown_triggers()


@pytest.mark.asyncio
async def test_prestart_cancel_and_protected_owner_pause():
    """验证开始前取消和插件暂停会正确等待临界操作，暂停期间拒绝新请求。"""
    background = BackgroundTaskRegistry()
    entry = CommandConfig.build()
    await entry.activate()
    owner = uuid4()
    dispatcher = ConfigManager()
    dispatcher.initialize_triggers(
        background, max_running=1, resolve_owner=lambda _: owner
    )
    try:
        uid = dispatcher.submit_trigger(entry, group="action", field="run", value=True)
        assert (
            dispatcher.submit_trigger(entry, group="action", field="run", value=False)
            == uid
        )
        assert await background.get_group("config-triggers").drain(1)
        assert dispatcher.trigger_result(uid).state == "cancelled"
        assert entry._calls == 0
        uid = dispatcher.submit_trigger(
            entry, group="action", field="fixed", value=True
        )
        await entry._started.wait()
        assert not dispatcher.prepare_trigger_restart()
        entered = asyncio.Event()

        async def pause():
            """进入插件暂停上下文并断言新增操作被拒绝，再通知测试已完成在途操作等待。"""
            async with dispatcher.pause_trigger_owners([owner]):
                entered.set()
                with pytest.raises(TriggerUnavailable, match="owner_stopping"):
                    dispatcher.submit_trigger(
                        entry, group="action", field="run", value=True
                    )

        waiter = asyncio.create_task(pause())
        await asyncio.sleep(0)
        assert not entered.is_set()
        entry._release.set()
        await waiter
        assert dispatcher.trigger_result(uid).state == "succeeded"
        assert dispatcher.prepare_trigger_restart()
        with pytest.raises(TriggerUnavailable, match="trigger_unavailable"):
            dispatcher.submit_trigger(entry, group="action", field="run", value=True)
        dispatcher.cancel_trigger_restart()
        uid = dispatcher.submit_trigger(entry, group="action", field="run", value=True)
        assert (
            dispatcher.submit_trigger(entry, group="action", field="run", value=False)
            == uid
        )
        assert await background.get_group("config-triggers").drain(1)
        assert dispatcher.trigger_result(uid).state == "cancelled"
    finally:
        await dispatcher.shutdown_triggers()


@pytest.mark.asyncio
async def test_sync_trigger_keeps_loop_responsive_and_clears_on_completion(
    monkeypatch, tmp_path
):
    """通过原生更新和 HTTP 查询验证线程阻塞、超时去重及事件回收。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from yaml import safe_load

    from app.api import config_triggers
    from app.config.core import entry

    patch = PlainConfig.model_validate({"action": {"run": True}})
    assert patch.action.run is None
    assert patch.model_dump(mode="python")["action"]["run"] is True
    config = PlainConfig.build()
    await config.activate()
    background = BackgroundTaskRegistry()
    manager = ConfigManager()
    manager.register_root(config, tmp_path / "config.yaml")
    manager.initialize_triggers(background, max_running=1)
    monkeypatch.setattr(entry, "config_manager", manager)
    monkeypatch.setattr(config_triggers, "config_manager", manager)
    app = FastAPI()
    app.include_router(config_triggers.router)

    try:
        assert config.action.run is None
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            body = {"configUid": str(config.uid), "group": "action", "field": "run"}
            noop = await client.post(
                "/api/config/triggers/write", json=body | {"value": None}
            )
            assert noop.json()["data"] is None
            for invalid in ("true", 1, str(config.uid)):
                response = await client.post(
                    "/api/config/triggers/write", json=body | {"value": invalid}
                )
                assert response.status_code == 422
            assert (
                await client.post("/api/config/triggers/write", json=body)
            ).status_code == 422
            await config.update(patch)
            uid = config.action.run
            assert isinstance(uid, UUID)
            async with asyncio.timeout(1):
                while not config._started.is_set():
                    await asyncio.sleep(0.005)
            await asyncio.sleep(0.08)
            current = await client.get("/api/config/triggers/active")
            assert [op["taskId"] for op in current.json()["data"]] == [str(uid)]
            duplicate = await client.post(
                "/api/config/triggers/write", json=body | {"value": True}
            )
            assert duplicate.json()["data"] == str(uid)
            assert not config._release.is_set()
            assert config._calls == 1
            await manager.flush()
            await manager.export(tmp_path / "backup")
            for file in (tmp_path / "config.yaml", tmp_path / "backup" / "config.yaml"):
                assert (
                    "run" not in safe_load(file.read_text(encoding="utf-8"))["action"]
                )
            assert config.model_dump(
                mode="json", context=ExportContext(audience="api")
            )["action"]["run"] == str(uid)
            hint = next(
                hint
                for hint in config._get_ui_hints()["action"]
                if hint["field"] == "run"
            )
            assert hint["state"] == "busy"
            assert hint["editable"] is False
            group = background.get_group("config-triggers")
            handle = manager._triggers[uid].handle
            config._release.set()
            assert await handle.wait_done(1)
            assert config.action.run is None
            assert (
                config.model_dump(mode="json", context=ExportContext(audience="api"))[
                    "action"
                ]["run"]
                is None
            )
            assert manager.active_triggers() == []
            assert group.query(handle) is None
            result = await client.post(
                "/api/config/triggers/result", json={"taskId": str(uid)}
            )
            assert result.json()["data"]["state"] == "timed_out"
            assert result.json()["data"]["errorCode"] == "TimeoutError"
            assert config._calls == 1
    finally:
        config._release.set()
        await manager.shutdown_triggers()


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", ["cancel", "pause", "shutdown"])
async def test_trigger_cleanup_precedes_lifecycle_return(waiting):
    """取消、插件停用和程序退出都等待字段完成回收。"""
    background = BackgroundTaskRegistry()
    config = CommandConfig.build()
    await config.activate()
    owner = uuid4()
    manager = ConfigManager()
    manager.initialize_triggers(
        background, max_running=1, resolve_owner=lambda _: owner
    )
    uid = manager.submit_trigger(config, group="action", field="run", value=True)
    await asyncio.wait_for(config._started.wait(), 1)
    try:
        if waiting == "cancel":
            assert (
                manager.submit_trigger(config, group="action", field="run", value=False)
                == uid
            )
            assert await background.get_group("config-triggers").drain(1)
        elif waiting == "pause":
            async with manager.pause_trigger_owners([owner]):
                assert config.action.run is None
        else:
            await manager.shutdown_triggers()
        assert config.action.run is None
        assert manager.trigger_result(uid).state == "cancelled"
    finally:
        await manager.shutdown_triggers()


@pytest.mark.asyncio
async def test_field_cancel_waits_for_protected_handler_and_skips_null(monkeypatch):
    from app.config.core import entry

    config = CommandConfig.build()
    await config.activate()
    background = BackgroundTaskRegistry()
    manager = ConfigManager()
    manager.initialize_triggers(background, max_running=1)
    monkeypatch.setattr(entry, "config_manager", manager)
    try:
        assert config.write_trigger("action", "fixed", False) is None
        uid = config.write_trigger("action", "fixed", True)
        await asyncio.wait_for(config._started.wait(), 1)
        await config.update(CommandConfig.model_validate({"action": {"fixed": None}}))
        assert manager.trigger_result(uid).state == "running"
        await config.update(CommandConfig.model_validate({"action": {"fixed": False}}))
        await asyncio.sleep(0)
        assert config.action.fixed == uid
        assert manager.trigger_result(uid).state == "cancelling"
        assert config.write_trigger("action", "fixed", True) == uid
        config._release.set()
        assert await background.get_group("config-triggers").drain(1)
        assert config.action.fixed is None
        assert manager.trigger_result(uid).state == "cancelled"
        assert config._calls == 1
    finally:
        config._release.set()
        await manager.shutdown_triggers()
