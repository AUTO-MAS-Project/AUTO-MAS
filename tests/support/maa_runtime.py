"""真实配置、运行树和调度入口；仅替换 MAA 进程与模拟器边界。"""

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest_asyncio
from auto_mas_core.host.utils import io
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.native.presets import get_maa_base_preset
from maa_adapter.tasks.manager import MaaManager

from app.config import ConfigCollection, config_manager
from app.core import Config
from app.core.background_tasks import BackgroundTaskRegistry
from app.core.task_manager import _TaskManager
from app.models.config import (
    GameEntry,
    PlanEntry,
    QueueConfig,
    ScriptEntry,
)
from app.models.config.plugin_emulator import EmulatorDeviceEntry, EmulatorEntry
from app.models.emulator import DeviceInfo, DeviceRef, DeviceStatus
from app.models.task import TaskMode
from app.plugin.base.emulator import EmulatorControl


@pytest_asyncio.fixture
async def runtime(monkeypatch, isolated_app_paths, tmp_path, tmp_path_factory):
    """构建隔离的真实配置、MAA 原生文件和宿主调度环境，以受控进程和模拟器替代外部程序，结束时清理任务。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_manager, "_collections", {})
    games = ConfigCollection[GameEntry].build([EmulatorEntry], name="games")
    await games.activate()
    eid = games.add(EmulatorEntry, payload={"info": {"name": "boundary emulator"}})
    await games.commit()
    device_id = games[eid].devices.add(EmulatorDeviceEntry)
    await games[eid].devices.commit()
    monkeypatch.setattr(Config, "GameConfig", games)
    from maa_adapter.plugin import Plugin as MaaPlugin

    from app.core import Plugin

    monkeypatch.setattr(Plugin, "script_types", {"maa": MaaPlugin.decl})
    scripts = ConfigCollection[ScriptEntry].build([MaaConfig], name="ScriptConfig")
    await scripts.activate()
    plans = ConfigCollection[PlanEntry].build([MaaPlanConfig], name="PlanConfig")
    await plans.activate()
    queues = ConfigCollection[QueueConfig].build([QueueConfig], name="QueueConfig")
    await queues.activate()
    monkeypatch.setattr(Config, "ScriptConfig", scripts)
    monkeypatch.setattr(Config, "PlanConfig", plans)
    monkeypatch.setattr(Config, "QueueConfig", queues)
    MaaUserConfig.related_config = {"PlanConfig": plans}
    install = tmp_path_factory.mktemp("maa-install")
    (install / "config").mkdir(parents=True)
    (install / "MAA.exe").write_bytes(b"process-boundary-fixture")
    for name in ("gui.json", "gui.new.json"):
        io.write_file(
            install / "config" / name,
            get_maa_base_preset() if name == "gui.new.json" else {},
        )
    (install / "resource/tasks").mkdir(parents=True)
    io.write_file(
        install / "resource/tasks/tasks.json", {"StartUpThemes": {"next": []}}
    )
    original = {
        name: (install / "config" / name).read_bytes()
        for name in ("gui.json", "gui.new.json")
    }
    sid = scripts.add(
        MaaConfig,
        payload={
            "Info": {"Name": "fresh MAA", "Path": str(install)},
            "game": {"game_id": str(eid), "device_id": str(device_id)},
        },
    )
    await scripts.commit()
    user = scripts[sid].users.add(
        MaaUserConfig,
        payload={
            "Info": {
                "Name": "native account",
                "Base": "native",
                "Status": True,
                "IfQuickConfig": False,
            }
        },
    )
    await scripts[sid].users.commit()
    assert scripts[sid].info.name == "fresh MAA"
    assert scripts[sid].users[user].info.enabled is True
    opened = []
    adb = install / "adb.exe"
    adb.write_bytes(b"adb-boundary-fixture")
    emulator = SimpleNamespace(
        open=AsyncMock(return_value=SimpleNamespace(adb_address="127.0.0.1:5555")),
        close=AsyncMock(),
        get_adb_path=lambda: adb,
    )

    class DeviceBoundary(EmulatorControl):
        async def refresh(self):
            pass

        async def open(self, uid, package=None, *, ticket):
            self.check_subscription(uid, ticket)
            await emulator.open(uid, package)

        async def close(self, uid, *, ticket):
            self.check_subscription(uid, ticket)
            await emulator.close(uid)

        async def show(self, uid, *, ticket):
            self.check_subscription(uid, ticket)

        hide = minimize = maximize = open_store = show

        async def launch_app(self, uid, package, *, ticket):
            self.check_subscription(uid, ticket)

        async def create_instance(self, name):
            raise NotImplementedError

        async def delete_instance(self, uid, *, ticket):
            raise NotImplementedError

        async def install_app(self, uid, path, *, ticket):
            raise NotImplementedError

        async def device_info(self, uid):
            return DeviceInfo(
                "boundary emulator", DeviceStatus.ONLINE, "127.0.0.1:5555"
            )

        def get_adb_path(self):
            return adb

        def resolve_device(self, uid):
            return DeviceRef("general", str(adb), "0")

    from app.core.game_manager import _GameManager

    _GameManager.create_control(config=games[eid], control_class=DeviceBoundary)

    class Process:
        async def open_process(self, executable, *args, **kwargs):
            """确认启动进程时托管配置已加锁，并记录要打开的程序路径。"""
            assert scripts[sid].is_locked
            opened.append(executable)

        main_pid = 100
        process = SimpleNamespace(wait=AsyncMock())

        async def is_running(self):
            """默认报告测试进程已退出，供配置会话无需真实 GUI 即可完成。"""
            return False

        async def close(self):
            """提供测试进程的空关闭入口，避免操作作者环境中的真实 MAA。"""
            pass

        async def kill(self):
            """提供测试进程的空强制停止入口，保留调度收尾调用路径。"""
            pass

    import maa_adapter.tasks.manager as manager_module
    import maa_adapter.tasks.session as worker_module

    monkeypatch.setattr(worker_module, "ProcessManager", Process)
    monkeypatch.setattr(
        manager_module.process, "kill_process", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        manager_module.process, "is_process_running", AsyncMock(return_value=False)
    )
    from app.core import Publisher

    monkeypatch.setattr(Publisher, "send", AsyncMock(return_value=True))
    monkeypatch.setattr("app.core.Power", SimpleNamespace(power_task=None))
    notify = MagicMock()
    notify.task_notification_batch.side_effect = lambda **kwargs: nullcontext()
    monkeypatch.setattr("app.task.script_expander.Notify", notify)
    background = BackgroundTaskRegistry()
    monkeypatch.setattr("app.core.BackgroundTaskManager", background)
    monkeypatch.setattr("app.task.prefetch.BackgroundTaskManager", background)
    monkeypatch.setattr("app.task.history_core.BackgroundTaskManager", background)
    manager = _TaskManager()
    monkeypatch.setattr("app.core.task_manager.TaskManager", manager)
    manager.plugin_expander = lambda runtime, config: MaaManager(runtime, config)
    state = SimpleNamespace(
        manager=manager,
        script=scripts[sid],
        user=scripts[sid].users[user],
        sid=sid,
        user_id=user,
        opened=opened,
        emulator=emulator,
        original=original,
        install=install,
        process=Process,
        started=asyncio.Event(),
    )
    import maa_adapter.tasks.auto_proxy as auto_module

    monkeypatch.setattr(auto_module, "ProcessManager", Process)
    monkeypatch.setattr(manager_module.stage_service, "get_stage", AsyncMock())
    from app.core import GameMaintenance, History, Notify

    monkeypatch.setattr(GameMaintenance, "get_active", AsyncMock(return_value=None))
    monkeypatch.setattr(manager_module, "push_maintenance_notice", AsyncMock())
    for method in ("send_notice", "push_statistics_report", "push_proxy_result"):
        monkeypatch.setattr(Notify, method, AsyncMock())
    state.record_history = AsyncMock()
    monkeypatch.setattr(History, "record", state.record_history)
    monkeypatch.setattr("app.services.capture_adb", AsyncMock(return_value=None))
    yield state
    for execution in list(manager.task_handler.values()):
        await execution.stop()
    await background.shutdown(timeout=2)


async def dispatch(state, mode, *, account=True):
    """按指定模式和账号范围组装任务树，通过真实任务管理器启动并返回执行对象。"""
    tree = {
        0: {
            "uid": str(state.sid),
            "children": {0: {"uid": str(state.user_id) if account else "default"}},
        }
    }
    if mode == TaskMode.AUTO_PROXY:
        tree = {0: {"uid": "-", "children": tree}}
    uid = await state.manager.start(mode, tree)
    return state.manager.task_handler[uid]
