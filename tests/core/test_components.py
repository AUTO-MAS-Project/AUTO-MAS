"""共享组件在不同导入顺序下保持唯一，启动模块不提前加载组件。"""

import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "order",
    [
        (
            "Config",
            "Community",
            "Notify",
            "EmulatorManager",
            "TaskManager",
            "Taskboard",
        ),
        (
            "Community",
            "EmulatorManager",
            "Config",
            "Taskboard",
            "Notify",
            "TaskManager",
        ),
        (
            "Notify",
            "TaskManager",
            "Taskboard",
            "Community",
            "Config",
            "EmulatorManager",
        ),
        (
            "EmulatorManager",
            "Config",
            "Notify",
            "Community",
            "TaskManager",
            "Taskboard",
        ),
    ],
)
def test_component_import_order_preserves_shared_identity(order):
    code = f"""
import importlib
import sys
import main
assert "app.core.config.manager" not in sys.modules
import app.core as core
names = {order!r}
instances = {{name: getattr(core, name) for name in names}}
modules = {{"Config": "config", "Community": "community", "Notify": "notify",
           "EmulatorManager": "emulator_manager", "TaskManager": "task_manager",
           "Taskboard": "taskboard"}}
for name, instance in instances.items():
    assert not isinstance(instance, type)
    assert getattr(core, name) is instance
    assert getattr(importlib.import_module("app.core." + modules[name]), name) is instance
assert "_transport" not in instances["Notify"].__dict__
old_instance_locations = {{
    "app.core.config.manager": "Config",
    "app.core.task_manager.manager": "TaskManager",
    "app.core.emulator_manager.manager": "EmulatorManager",
    "app.core.community.manager": "Community",
    "app.core.notify.manager": "Notify",
    "app.core.ws.manager": "MainConnection",
    "app.core.ws.dispatcher": "Dispatcher",
    "app.core.ws.publisher": "Publisher",
}}
for module, name in old_instance_locations.items():
    assert not hasattr(importlib.import_module(module), name), (module, name)
for name, module in {{
    "DesktopGuard": "desktop_guard", "History": "history", "I18n": "i18n",
    "Taskboard": "taskboard", "Dispatcher": "ws", "MainConnection": "ws",
    "Publisher": "ws",
    "MainTimer": "timer", "RuntimeTasks": "runtime_tasks",
    "GameCalendar": "game_calendar", "GameMaintenance": "game_maintenance",
    "Updater": "update", "ShutdownCoordinator": "lifecycle",
}}.items():
    instance = getattr(core, name)
    assert not isinstance(instance, type)
    assert getattr(importlib.import_module("app.core." + module), name) is instance
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_community_flow_excludes_concurrent_callers_and_releases_after_use():
    import asyncio

    from app.core import Community
    from app.tools.common.community.contracts import CommunitySignInProgressError

    async def enter() -> bool:
        try:
            async with Community.community_sign_flow():
                return True
        except CommunitySignInProgressError:
            return False

    async with Community.community_sign_flow():
        assert await asyncio.create_task(enter()) is False
    assert await asyncio.create_task(enter()) is True


@pytest.mark.asyncio
async def test_community_cache_subscription_is_repeatable_and_invalidates_once():
    from app.core.community.activity import _ActivityCacheEntry
    from app.core.community.manager import CommunityManager
    from app.models.config import GameSignAccountGroup, GlobalConfig, ToolsConfig
    from tests.config_support import activate_config

    tools = ToolsConfig.build()
    setting = GlobalConfig.build()
    await activate_config(tools)
    await activate_config(setting)
    community = CommunityManager()
    receiver = community._invalidate_activity_cache
    try:
        community.connect_community_activity_cache(tools, setting=setting)
        community.connect_community_activity_cache(tools, setting=setting)
        revision = community._activity_cache_revision
        community._activity_cache[(0, "test")] = _ActivityCacheEntry(
            snapshots=(), expires_at=0
        )
        await tools.update(
            ToolsConfig.model_validate(
                {"GameSign": {"ActivityEnabled": not tools.GameSign.ActivityEnabled}}
            ),
            check_visibility=False,
        )
        assert community._activity_cache == {}
        assert community._activity_cache_revision == revision + 1
    finally:
        GameSignAccountGroup.disconnect(
            receiver, phase="runtime", group="GameSignAccount"
        )
        tools.GameSign_Accounts.disconnect(receiver, phase="runtime")
        tools.disconnect(
            receiver, phase="runtime", group="GameSign", field="ActivityEnabled"
        )
        setting.disconnect(
            receiver, phase="runtime", group="Update", field="ProxyAddress"
        )
