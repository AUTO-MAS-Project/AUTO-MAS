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
    """在独立进程中验证不同导入顺序仍复用同一宿主组件，且惰性入口不提前初始化配置。"""
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
    "MainTimer": "timer", "BackgroundTaskManager": "background_tasks",
    "GameCalendar": "game_calendar", "GameMaintenance": "game_maintenance",
    "Downloads": "downloads", "Operations": "plugin.operations",
    "Plugin": "plugin", "GameManager": "game_manager",
    "ShutdownCoordinator": "lifecycle",
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
