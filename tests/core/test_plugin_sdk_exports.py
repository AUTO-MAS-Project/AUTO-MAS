"""SDK 宿主出口契约：插件经 ``auto_mas_core.host`` 取到的就是宿主自己的对象。

插件包只能经 SDK 复用宿主能力；出口取不到或取到的不是宿主那一份时，插件只好退回直接导入
``app.*``，或者拿到一份和宿主判断对不上的副本（基类、模块状态）。
"""

import importlib
import sys

import pytest

_PLATFORM_PROCESS = (
    "app.utils.windows.process"
    if sys.platform == "win32"
    else "app.utils.common.process.platform"
)


@pytest.mark.parametrize(
    ("facade", "name", "host_module"),
    [
        (
            "core_notify_formats_maafw",
            "build_statistics_payload",
            "app.core.notify.formats.maafw",
        ),
        ("core_notify_lifecycle", "NotificationTaskBase", "app.core.notify.lifecycle"),
        (
            "utils_common_game_resolution",
            "UnityGameResolutionOverride",
            "app.utils.common.game_resolution",
        ),
        (
            "utils_common_game_resolution",
            "parse_resolution_option",
            "app.utils.common.game_resolution",
        ),
    ],
)
def test_facade_exports_host_object(facade: str, name: str, host_module: str) -> None:
    """插件从出口取名字，得到宿主模块里的同一个对象。"""
    exported = getattr(importlib.import_module(f"auto_mas_core.host.{facade}"), name)

    assert exported is getattr(importlib.import_module(host_module), name)


@pytest.mark.parametrize(
    ("facade", "name", "host_module"),
    [
        ("utils", "process_platform", _PLATFORM_PROCESS),
        ("utils_common", "game_window", "app.utils.common.game_window"),
        ("services_gi_updater", "genshin", "app.services.common.gi_updater.genshin"),
        ("services", "telemetry", "app.services.common.telemetry"),
        ("services_common_update", "transport", "app.services.common.update.transport"),
    ],
)
def test_facade_exports_host_submodule(
    facade: str, name: str, host_module: str
) -> None:
    """宿主包里还没被导入过的子模块，也能经出口取到宿主那一份模块对象。"""
    exported = getattr(importlib.import_module(f"auto_mas_core.host.{facade}"), name)

    assert exported is importlib.import_module(host_module)


def test_notification_task_base_is_inheritable_host_class() -> None:
    """专项 manager 继承出口给的基类，宿主按自己的基类认得出它。"""
    from auto_mas_core.host.core_notify_lifecycle import NotificationTaskBase

    from app.core.notify.lifecycle import NotificationTaskBase as HostBase
    from app.models.task import TaskExecuteBase

    class Manager(NotificationTaskBase):
        pass

    assert issubclass(Manager, HostBase)
    assert issubclass(Manager, TaskExecuteBase)


def test_busy_error_is_host_class() -> None:
    """插件按 SDK 给的类认「调用门暂停、注册表已封」，宿主抛的就是这个类。"""
    import auto_mas_core

    from app.plugin.errors import PluginBusyError

    assert auto_mas_core.PluginBusyError is PluginBusyError
    assert "PluginBusyError" in auto_mas_core.__all__


def test_restricted_facade_rejects_unlisted_name() -> None:
    """只开放 ``__all__`` 的出口不放出宿主模块里别的名字。"""
    module = importlib.import_module("auto_mas_core.host.utils_common_game_resolution")

    with pytest.raises(AttributeError):
        getattr(module, "read_unity_resolution")
