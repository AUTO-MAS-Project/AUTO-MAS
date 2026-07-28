from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest_asyncio

from app.core import task_manager as task_manager_module
from app.core.config import AppConfig
from app.core.script_types import (
    ScriptRecordCapability,
    ScriptTypeProvider,
    script_type_registry,
)
from app.core.task_manager import TaskManager
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.plugins.manager import PluginManager


Behavior = Literal["success", "fail", "crash", "block"]


class MessageCollector:
    """Collect WebSocket envelopes emitted by the task manager."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.changed = asyncio.Event()

    async def __call__(self, id: str, type: str, data: dict[str, Any]) -> None:
        self.messages.append({"id": str(id), "type": type, "data": data})
        self.changed.set()

    async def wait_for(
        self,
        predicate: Callable[[dict[str, Any]], bool],
        *,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            while True:
                for message in self.messages:
                    if predicate(message):
                        return message
                self.changed.clear()
                await self.changed.wait()


@dataclass
class LifecycleControl:
    behavior: Behavior = "success"
    started: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    finalized: asyncio.Event = field(default_factory=asyncio.Event)
    crashed: asyncio.Event = field(default_factory=asyncio.Event)
    crash_error: Exception | None = None


class ControllableManager(TaskExecuteBase):
    """Deterministic script manager used at the external script-engine boundary."""

    def __init__(
        self,
        script_info: ScriptItem,
        control: LifecycleControl,
        *,
        config: Any | None = None,
        adapter_type: str = "General",
    ) -> None:
        super().__init__()
        self.script_info = script_info
        self.control = control
        self.config = config
        self.adapter_type = adapter_type

    def _load_created_users(self) -> None:
        if self.config is None:
            return

        script_config = self.config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ]
        self.script_info.user_list = [
            UserItem(
                user_id=str(user_id),
                name=user_config.get("Info", "Name"),
                status="等待",
            )
            for user_id, user_config in script_config.UserData.items()
        ]

    async def main_task(self) -> None:
        self._load_created_users()
        self.script_info.status = "运行"
        for user in self.script_info.user_list:
            user.status = "运行中"
        self.control.started.set()
        await asyncio.sleep(0)

        if self.control.behavior == "crash":
            if self.config is None:
                raise RuntimeError("模拟运行时崩溃")
            raise RuntimeError(f"模拟 {self.adapter_type} 运行时异常")

        await self.control.release.wait()
        if self.control.behavior == "fail":
            self.script_info.status = "异常"
            for user in self.script_info.user_list:
                user.status = "失败"
            if self.config is not None and self.script_info.task_info is not None:
                await self.config.send_websocket_message(
                    id=self.script_info.task_info.task_id,
                    type="Info",
                    data={"Error": f"模拟 {self.adapter_type} 任务失败"},
                )
        else:
            self.script_info.status = "完成"
            for user in self.script_info.user_list:
                user.status = "完成"
        await asyncio.sleep(0)

    async def final_task(self) -> None:
        self.script_info.log += "\n[测试] final_task 已执行"
        self.control.finalized.set()

    async def on_crash(self, error: Exception) -> None:
        self.control.crash_error = error
        self.control.crashed.set()
        self.script_info.status = "异常"
        for user in self.script_info.user_list:
            user.status = "异常"
        self.script_info.log += f"\n[测试] {type(error).__name__}: {error}"
        if self.config is not None and self.script_info.task_info is not None:
            await self.config.send_websocket_message(
                id=self.script_info.task_info.task_id,
                type="Info",
                data={"Error": f"{type(error).__name__}: {error}"},
            )


@dataclass
class LifecycleHarness:
    script_id: str
    collector: MessageCollector
    control: LifecycleControl


@dataclass
class SpecializedLifecycleHarness:
    adapter_type: str
    collector: MessageCollector
    control: LifecycleControl
    config: AppConfig


def _build_plugin_provider(adapter_type: str) -> ScriptTypeProvider:
    if adapter_type == "OkScript":
        from ok_script_adapter.plugin import Plugin
    elif adapter_type == "Okww":
        from okww_adapter.plugin import Plugin
    else:
        raise ValueError(f"不支持的插件专项类型: {adapter_type}")

    plugin = Plugin(SimpleNamespace())
    for definition in plugin.build_script_adapters():
        if definition.type_key == adapter_type:
            return definition.build_provider(owner="task-lifecycle-test")
    raise LookupError(f"未找到专项适配 provider: {adapter_type}")


def _get_specialized_provider(adapter_type: str) -> ScriptTypeProvider:
    if adapter_type in {"OkScript", "Okww"}:
        return _build_plugin_provider(adapter_type)
    return script_type_registry.get(adapter_type)


async def _restore_task_manager(
    original_task_info: dict,
    original_task_handler: dict,
) -> None:
    for task_id, handler in list(TaskManager.task_handler.items()):
        if task_id in original_task_handler:
            continue
        handler.cancel()
        try:
            async with asyncio.timeout(2.0):
                await handler.accomplish.wait()
        except TimeoutError:
            pass

    TaskManager.task_info.clear()
    TaskManager.task_info.update(original_task_info)
    TaskManager.task_handler.clear()
    TaskManager.task_handler.update(original_task_handler)


@pytest_asyncio.fixture
async def lifecycle_harness(monkeypatch) -> AsyncIterator[LifecycleHarness]:
    """Install a reversible task environment for one lifecycle test."""

    collector = MessageCollector()
    control = LifecycleControl()
    script_uuid = uuid.uuid4()
    script_config = GeneralConfig()

    async def get_capability(_: uuid.UUID) -> ScriptRecordCapability:
        return ScriptRecordCapability(
            available=True,
            supported_modes=("AutoProxy", "ScriptConfig"),
        )

    config = SimpleNamespace(
        ScriptConfig={script_uuid: script_config},
        QueueConfig={},
        power_sign="NoAction",
        send_websocket_message=collector,
        get_script_record_capability=get_capability,
    )
    monkeypatch.setattr(task_manager_module, "Config", config)
    monkeypatch.setattr(PluginManager, "emit_async", AsyncMock())

    from app.api import dispatch as dispatch_module
    from app.core.timer import MainTimer

    monkeypatch.setattr(dispatch_module, "Config", config)
    monkeypatch.setattr(dispatch_module, "TaskManager", TaskManager)
    monkeypatch.setattr(MainTimer, "try_game_sign_for_task", AsyncMock())

    original_task_info = TaskManager.task_info.copy()
    original_task_handler = TaskManager.task_handler.copy()
    try:
        original_provider = script_type_registry.get("General")
        original_owner = script_type_registry.get_owner("General")
    except KeyError:
        original_provider = None
        original_owner = None

    script_type_registry.unregister("General")
    provider = ScriptTypeProvider(
        type_key="General",
        display_name="通用脚本（测试）",
        script_config_class=GeneralConfig,
        user_config_class=GeneralUserConfig,
        supported_modes=("AutoProxy", "ScriptConfig"),
        manager_factory=lambda item: ControllableManager(item, control),
        is_builtin=True,
    )
    script_type_registry.register(provider, owner="task-lifecycle-test")

    try:
        yield LifecycleHarness(
            script_id=str(script_uuid),
            collector=collector,
            control=control,
        )
    finally:
        await _restore_task_manager(original_task_info, original_task_handler)

        script_type_registry.unregister("General", owner="task-lifecycle-test")
        if original_provider is not None:
            script_type_registry.register(original_provider, owner=original_owner)


@pytest_asyncio.fixture
async def specialized_lifecycle_harness(
    request,
    monkeypatch,
    tmp_path,
) -> AsyncIterator[SpecializedLifecycleHarness]:
    """Create one specialized script environment through its real provider."""

    adapter_type = str(request.param)
    collector = MessageCollector()
    control = LifecycleControl()
    original_task_info = TaskManager.task_info.copy()
    original_task_handler = TaskManager.task_handler.copy()

    try:
        original_provider = script_type_registry.get(adapter_type)
        original_owner = script_type_registry.get_owner(adapter_type)
    except KeyError:
        original_provider = None
        original_owner = None

    provider = replace(_get_specialized_provider(adapter_type))
    if original_provider is not None:
        script_type_registry.unregister(adapter_type)

    try:
        script_type_registry.register(provider, owner="task-lifecycle-test")
        monkeypatch.chdir(tmp_path)
        config = AppConfig()
        provider.manager_factory = lambda item: ControllableManager(
            item,
            control,
            config=config,
            adapter_type=adapter_type,
        )

        config.send_websocket_message = collector
        monkeypatch.setattr(task_manager_module, "Config", config)
        monkeypatch.setattr(PluginManager, "emit_async", AsyncMock())

        from app.api import dispatch as dispatch_module
        from app.api import scripts2 as scripts2_module
        from app.core.timer import MainTimer

        monkeypatch.setattr(dispatch_module, "Config", config)
        monkeypatch.setattr(dispatch_module, "TaskManager", TaskManager)
        monkeypatch.setattr(scripts2_module, "Config", config)
        monkeypatch.setattr(MainTimer, "try_game_sign_for_task", AsyncMock())

        yield SpecializedLifecycleHarness(
            adapter_type=adapter_type,
            collector=collector,
            control=control,
            config=config,
        )
    finally:
        await _restore_task_manager(original_task_info, original_task_handler)
        script_type_registry.unregister(adapter_type, owner="task-lifecycle-test")
        if original_provider is not None:
            script_type_registry.register(original_provider, owner=original_owner)
