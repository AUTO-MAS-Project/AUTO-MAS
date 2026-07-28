from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest_asyncio

from app.core import task_manager as task_manager_module
from app.core.script_types import (
    ScriptRecordCapability,
    ScriptTypeProvider,
    script_type_registry,
)
from app.core.task_manager import TaskManager
from app.models.config import GeneralConfig, GeneralUserConfig
from app.models.task import ScriptItem, TaskExecuteBase
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

    def __init__(self, script_info: ScriptItem, control: LifecycleControl) -> None:
        super().__init__()
        self.script_info = script_info
        self.control = control

    async def main_task(self) -> None:
        self.script_info.status = "运行"
        for user in self.script_info.user_list:
            user.status = "运行中"
        self.control.started.set()
        await asyncio.sleep(0)

        if self.control.behavior == "crash":
            raise RuntimeError("模拟运行时崩溃")

        await self.control.release.wait()
        if self.control.behavior == "fail":
            self.script_info.status = "异常"
            for user in self.script_info.user_list:
                user.status = "失败"
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
        self.script_info.log += f"\n[测试] {type(error).__name__}: {error}"


@dataclass
class LifecycleHarness:
    script_id: str
    collector: MessageCollector
    control: LifecycleControl


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

        script_type_registry.unregister("General", owner="task-lifecycle-test")
        if original_provider is not None:
            script_type_registry.register(original_provider, owner=original_owner)
