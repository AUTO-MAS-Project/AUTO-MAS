"""真实配置、运行树和调度入口；仅替换 MAA 进程与模拟器边界。"""

import asyncio
from contextlib import nullcontext
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from auto_mas_core.host.utils import io
from maa_adapter import PLUGIN
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
    EmulatorConfig,
    GameEntry,
    PlanEntry,
    QueueConfig,
    ScriptEntry,
)
from app.models.task import TaskMode


@pytest_asyncio.fixture
async def runtime(monkeypatch, isolated_app_paths, tmp_path, tmp_path_factory):
    """构建隔离的真实配置、MAA 原生文件和宿主调度环境，以受控进程和模拟器替代外部程序，结束时清理任务。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_manager, "_collections", {})
    games = ConfigCollection[GameEntry].build([GameEntry], name="games")
    await games.activate()
    emulator_configs = ConfigCollection[EmulatorConfig].build(
        [EmulatorConfig], name="EmulatorConfig"
    )
    await emulator_configs.activate()
    eid = emulator_configs.add(
        EmulatorConfig, payload={"Info": {"Name": "boundary emulator"}}
    )
    await emulator_configs.commit()
    monkeypatch.setattr(Config, "EmulatorConfig", emulator_configs)
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
            "Emulator": {"Id": str(eid), "Index": "0"},
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
    monkeypatch.setattr(
        manager_module.EmulatorManager,
        "get_emulator_instance",
        AsyncMock(return_value=emulator),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [TaskMode.SCRIPT_CONFIG, TaskMode.SCRIPT_VIEW])
@pytest.mark.parametrize("account", [True, False])
async def test_session_uses_real_dispatch_and_preserves_native_config(
    runtime, mode, account
):
    """验证配置与查看会话经过真实 L2 至 L4 调度，并在结束后保留原安装的原生配置。"""
    runtime.user.Info.Status = False
    runtime.user.Info.RemainedDay = 0
    await runtime.user.commit()
    execution = await dispatch(runtime, mode, account=account)
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.error is None
    assert execution.task_info.info.status == "success", [
        (x.info.status, x.current.log) for x in execution.task_info.scripts.values()
    ]
    assert len(runtime.opened) == 1
    assert not runtime.script.is_locked
    assert not runtime.user.is_locked
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome, check_game_update",
    [("success", False), ("error", False), ("cancelled", False), ("success", True)],
)
async def test_auto_proxy_through_real_dispatch(
    runtime, monkeypatch, outcome, check_game_update
):
    """使用受控日志驱动自动代理成功、异常或取消结果，验证真实调度及原生配置恢复。"""
    import maa_adapter.tasks.auto_proxy as auto_module
    import maa_adapter.tasks.manager as manager_module

    from app.core import Publisher
    from app.core.ws import protocol
    from app.models.emulator import DeviceStatus
    from app.utils.common.game_update import GameUpdateResult

    startup_logs = []
    maa_start_logs = []
    monitor_ready_logs = []
    runtime.script.Run.IfCheckGameUpdate = check_game_update
    runtime.emulator.getStatus = AsyncMock(return_value=DeviceStatus.OFFLINE)
    monkeypatch.setattr(
        manager_module,
        "ensure_game_updated",
        AsyncMock(
            return_value=GameUpdateResult(status="UpToDate", message="Game up to date")
        ),
    )

    async def open_emulator(*args, **kwargs):
        """在模拟器启动边界保存当前可见日志，核对启动提示已先于设备等待推送。"""
        snapshot = runtime.manager.get_runtime_snapshot().tasks[0]
        pushed = [
            call.kwargs["data"].log
            for call in Publisher.send.await_args_list
            if call.kwargs["type"] == protocol.TASK_LOG_UPDATED
        ]
        startup_logs.append((snapshot.log, pushed[-1] if pushed else None))
        await asyncio.sleep(0)
        startup_logs.append(
            (
                runtime.manager.get_runtime_snapshot().tasks[0].log,
                pushed[-1] if pushed else None,
            )
        )
        return SimpleNamespace(adb_address="127.0.0.1:5555")

    runtime.emulator.open.side_effect = open_emulator

    class Process(runtime.process):
        async def open_process(self, executable, *args, **kwargs):
            """记录 MAA 启动入口的正文，确认模拟器提示保留到真正启动 MAA。"""
            maa_start_logs.append(runtime.manager.get_runtime_snapshot().tasks[0].log)
            await super().open_process(executable, *args, **kwargs)

        async def is_running(self):
            """报告模拟 MAA 进程正在运行，允许自动代理进入日志观察流程。"""
            return True

    monkeypatch.setattr(auto_module, "ProcessManager", Process)

    class Monitor:
        def __init__(self, interval, fmt, callback, **kwargs):
            """保存来源日志回调，供测试注入本次运行结果。"""
            self.callback = callback

        async def start_monitor_file(self, *args, **kwargs):
            """标记自动代理已启动，并向实际日志回调注入当前场景的 MAA 输出。"""
            runtime.started.set()
            monitor_ready_logs.append(
                runtime.manager.get_runtime_snapshot().tasks[0].log
            )
            line = {
                "success": "任务已全部完成！",
                "error": "未选择任务",
                "cancelled": "正在执行任务",
            }[outcome]
            await self.callback([line], datetime.now().astimezone())

        async def stop(self):
            """提供测试日志观察器的空停止入口，保持正常收尾协议。"""
            pass

    monkeypatch.setattr(auto_module, "LogMonitor", Monitor)
    runtime.script.Run.RunTimesLimit = 1
    await runtime.script.commit()
    execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    if outcome == "cancelled":
        await asyncio.wait_for(runtime.started.wait(), timeout=10)
        await execution.stop()
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.error is None
    assert execution.task_info.info.status == outcome, [
        (
            x.info.status,
            x.current.log,
            [(u.info.status, u.info.result) for u in x.users.values()],
        )
        for x in execution.task_info.scripts.values()
    ]
    assert runtime.emulator.open.await_count == (2 if check_game_update else 1)
    assert startup_logs == [("正在启动模拟器\n", "正在启动模拟器\n")] * (
        4 if check_game_update else 2
    )
    assert maa_start_logs == ["正在启动模拟器\n"]
    assert monitor_ready_logs == [""]
    native_log = {
        "success": "任务已全部完成！",
        "error": "未选择任务",
        "cancelled": "正在执行任务",
    }[outcome]
    assert any(
        call.kwargs["type"] == protocol.TASK_LOG_UPDATED
        and call.kwargs["data"].log == native_log
        for call in Publisher.send.await_args_list
    )
    assert runtime.emulator.close.await_count >= 1
    assert not runtime.script.is_locked
    assert not runtime.user.is_locked
    assert runtime.user.Data.ProxyTimes == (1 if outcome == "success" else 0)
    assert runtime.record_history.await_count == 1
    record = runtime.record_history.call_args.args[0]
    assert record.status == outcome
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original


def test_plugin_declares_only_real_modes_and_prefetch():
    """验证插件只声明实际实现的自动代理、配置和查看模式，同时绑定预下载及真实配置类型。"""
    plugin = PLUGIN()
    assert plugin.decl.supported_modes == (
        TaskMode.AUTO_PROXY,
        TaskMode.SCRIPT_CONFIG,
        TaskMode.SCRIPT_VIEW,
    )
    assert plugin.decl.prefetch_check is not None
    assert plugin.decl.script_type is MaaConfig


@pytest.mark.asyncio
async def test_maintenance_skips_without_opening_device(runtime, monkeypatch):
    """验证处于维护时段的账号直接跳过，不打开模拟器且任务结束后释放配置锁。"""
    from app.core import GameMaintenance

    monkeypatch.setattr(
        GameMaintenance,
        "get_active",
        AsyncMock(return_value=SimpleNamespace(reason="维护中")),
    )
    execution = await dispatch(runtime, TaskMode.AUTO_PROXY)
    await asyncio.wait_for(execution.accomplish.wait(), timeout=10)
    assert execution.task_info.info.status == "success"
    script = next(iter(execution.task_info.scripts.values()))
    assert script.info.status == "跳过"
    assert next(iter(script.users.values())).info.status == "跳过"
    runtime.emulator.open.assert_not_awaited()
    assert not runtime.script.is_locked


@pytest.mark.asyncio
async def test_cancel_gui_with_unconfirmed_save_preserves_source(runtime, monkeypatch):
    """验证 GUI 取消后保存尚未确认时保留源配置，同时完成宿主锁的收尾。"""
    import maa_adapter.tasks.session as worker_module

    class Process(runtime.process):
        opened = False

        async def open_process(self, *args, **kwargs):
            """复用启动记录并标记 GUI 已打开，通知测试可以发起停止。"""
            await super().open_process(*args, **kwargs)
            self.opened = True
            runtime.started.set()

        async def is_running(self):
            """返回模拟 GUI 是否已打开，供停止保存确认检查使用。"""
            return self.opened

        async def close(self):
            """让已打开 GUI 的关闭持续等待，模拟无法确认正常保存退出的场景。"""
            if self.opened:
                await asyncio.Event().wait()

    monkeypatch.setattr(worker_module, "ProcessManager", Process)
    monkeypatch.setattr(worker_module.MaaGuiSession, "GUI_CLOSE_TIMEOUT", 0.01)
    execution = await dispatch(runtime, TaskMode.SCRIPT_CONFIG, account=False)
    await asyncio.wait_for(runtime.started.wait(), timeout=10)
    await asyncio.wait_for(execution.stop(), timeout=5)
    assert execution.task_info.info.status == "cancelled"
    assert {
        name: (runtime.install / "config" / name).read_bytes()
        for name in runtime.original
    } == runtime.original
    assert not runtime.script.is_locked


@pytest.mark.asyncio
async def test_migrated_maa_keeps_native_notification_policy(runtime):
    """验证迁入插件的 MAA 仍采用来源 Notify 分组控制用户统计通知。"""
    from app.core.notify.manager import NotificationManager

    runtime.user.Notify.Enabled = True
    runtime.user.Notify.IfSendStatistic = True
    await runtime.user.commit()
    assert not runtime.user.notify.enabled
    notify = NotificationManager()
    assert len(notify.user_statistic_targets(runtime.user)) == 1
    runtime.user.Notify.Enabled = False
    await runtime.user.commit()
    assert notify.user_statistic_targets(runtime.user) == []
