"""本地验证：首阶段下载触发阶段间更新，不提交专项一次性测试。"""

import asyncio
import importlib
import json
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models.task import LogRecord, UserItem
from app.task.MaaEnd import update_takeover as update

proxy = importlib.import_module("app.task.MaaEnd.AutoProxy")


def write_log(root: Path, content: str, *, name: str = "2026-09-30-1.log") -> Path:
    path = root / "debug" / name
    path.parent.mkdir(exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(content)
    return path


def write_installation(root: Path, *, version: str = "v1.0.0") -> Path:
    (root / "interface.json").write_text(json.dumps({"version": version}))
    path = root / "config" / "mxu-MaaEnd.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({"settings": {"autoRunOnLaunch": True}}))
    return path


@pytest.mark.asyncio
async def test_historical_download_and_version_check_do_not_insert_update(
    tmp_path, monkeypatch
):
    write_log(tmp_path, "开始下载更新: old\n更新安装完成\n")
    offsets = update.snapshot_mxu_logs(tmp_path)
    write_log(tmp_path, "发现新版本: v1.1.0\n")
    run = AsyncMock()
    monkeypatch.setattr(update, "_run_update_session", run)

    assert await update.update_maaend_after_stage(tmp_path, offsets) is None
    run.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "signal", ["开始下载更新: url", "更新下载完成", "检测到待安装更新: v1.1.0"]
)
async def test_new_download_inserts_update_once(tmp_path, monkeypatch, signal):
    offsets = update.snapshot_mxu_logs(tmp_path)
    write_log(tmp_path, f"发现新版本: v1.1.0\n{signal}\n")
    run = AsyncMock(return_value="v1.1.0")
    monkeypatch.setattr(update, "_run_update_session", run)

    assert await update.update_maaend_after_stage(tmp_path, offsets) == "v1.1.0"
    run.assert_awaited_once_with(
        root_path=tmp_path, target_version="v1.1.0", on_status=None
    )
    assert await update.update_maaend_after_stage(tmp_path, offsets) is None


@pytest.mark.asyncio
async def test_completed_installation_does_not_launch_again(tmp_path, monkeypatch):
    write_installation(tmp_path, version="v1.1.0")
    offsets = update.snapshot_mxu_logs(tmp_path)
    write_log(tmp_path, "发现新版本: v1.1.0\n开始下载更新: url\n更新安装完成\n")
    run = AsyncMock()
    monkeypatch.setattr(update, "_run_update_session", run)

    assert await update.update_maaend_after_stage(tmp_path, offsets) == "v1.1.0"
    run.assert_not_awaited()


@pytest.mark.asyncio
async def test_completed_message_requires_matching_installed_version(tmp_path):
    write_installation(tmp_path)
    offsets = update.snapshot_mxu_logs(tmp_path)
    write_log(tmp_path, "发现新版本: v1.1.0\n开始下载更新: url\n更新安装完成\n")
    with pytest.raises(update.MaaEndUpdateError, match="未达到"):
        await update.update_maaend_after_stage(tmp_path, offsets)


def test_log_reader_keeps_half_line_and_reads_new_file(tmp_path):
    write_log(tmp_path, "旧日志\n")
    offsets = update.snapshot_mxu_logs(tmp_path)
    write_log(tmp_path, "开始下载更")
    assert update._read_new_mxu_logs(tmp_path, offsets) == []
    write_log(tmp_path, "新: url\n")
    write_log(tmp_path, "更新安装完成\n", name="2026-09-30-2.log")
    assert update._read_new_mxu_logs(tmp_path, offsets) == [
        "开始下载更新: url",
        "更新安装完成",
    ]


@pytest.mark.parametrize(
    "initial",
    [
        {},
        {"settings": {}},
        {"settings": {"autoRunOnLaunch": True}},
        {"settings": {"autoRunOnLaunch": False}},
    ],
)
def test_auto_run_restored_and_native_changes_preserved(tmp_path, initial):
    config = tmp_path / "mxu-MaaEnd.json"
    config.write_text(json.dumps(initial))
    with update._pause_auto_run(config):
        active = json.loads(config.read_text())
        assert active["settings"]["autoRunOnLaunch"] is False
        active["settings"]["language"] = "zh-CN"
        config.write_text(json.dumps(active))
    restored = json.loads(config.read_text())
    assert restored["settings"] == {**initial.get("settings", {}), "language": "zh-CN"}


def fake_update_process(monkeypatch, root, on_start):
    config = write_installation(root)
    events = []

    class Process:
        def __init__(self):
            self.process = SimpleNamespace(pid=10, returncode=None)
            self.target_process = None

        async def open_process(self, executable, *args, **kwargs):
            assert executable == root / "MaaEnd.exe"
            assert args == ()
            assert (
                json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is False
            )
            events.append("open")
            await on_start(self)

        async def hide_window(self):
            events.append("hide")

        async def kill(self):
            assert (
                json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is False
            )
            events.append("kill")

    async def stop(executable):
        events.append("stop")

    monkeypatch.setattr(update, "ProcessManager", Process)
    monkeypatch.setattr(update, "_stop_mxu", stop)
    return config, events


@pytest.mark.asyncio
async def test_update_session_waits_for_install_and_restart(tmp_path, monkeypatch):
    async def start(process):
        write_log(tmp_path, "检测到待安装更新: v1.1.0\n更新安装完成\n")
        (tmp_path / "interface.json").write_text('{"version":"v1.1.0"}')
        process.process.returncode = 0

    config, events = fake_update_process(monkeypatch, tmp_path, start)
    child = SimpleNamespace(pid=11, create_time=time.time)
    monkeypatch.setattr(update, "_find_executable_processes", lambda _: [child])

    assert await update._run_update_session(tmp_path, "v1.1.0", None) == "v1.1.0"
    assert "hide" in events
    assert events[-2:] == ["kill", "stop"]
    assert json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message", ["更新安装失败", "更新下载失败", "检查更新失败: offline"]
)
async def test_update_failure_restores_settings(tmp_path, monkeypatch, message):
    async def start(process):
        write_log(tmp_path, message + "\n")

    config, events = fake_update_process(monkeypatch, tmp_path, start)
    with pytest.raises(update.MaaEndUpdateError, match="更新失败"):
        await update._run_update_session(tmp_path, "v1.1.0", None)
    assert events[-2:] == ["kill", "stop"]
    assert json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is True


@pytest.mark.asyncio
async def test_update_cancel_stops_before_restoring_settings(tmp_path, monkeypatch):
    started = asyncio.Event()

    async def start(process):
        started.set()
        await asyncio.Event().wait()

    config, events = fake_update_process(monkeypatch, tmp_path, start)
    task = asyncio.create_task(update._run_update_session(tmp_path, "v1.1.0", None))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events[-2:] == ["kill", "stop"]
    assert json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is True


@pytest.mark.asyncio
async def test_install_message_without_restart_is_not_success(tmp_path, monkeypatch):
    async def start(process):
        write_log(tmp_path, "更新安装完成\n")
        process.process.returncode = 0

    config, _ = fake_update_process(monkeypatch, tmp_path, start)
    monkeypatch.setattr(update, "_find_executable_processes", lambda _: [])
    monkeypatch.setattr(update, "_PROCESS_RESTART_TIMEOUT", 0)
    with pytest.raises(update.MaaEndUpdateError, match="重启完成"):
        await update._run_update_session(tmp_path, "v1.1.0", None)
    assert json.loads(config.read_text())["settings"]["autoRunOnLaunch"] is True


def make_proxy(monkeypatch, root):
    task = proxy.AutoProxyTask.__new__(proxy.AutoProxyTask)
    task.task_info = SimpleNamespace()
    task.script_info = SimpleNamespace(log="", name="MaaEnd")
    task.cur_user_item = UserItem(user_id="user", name="用户", status="等待")
    task.cur_user_uid = "user"
    task.cur_user_config = SimpleNamespace(
        get=lambda *args: "" if args == ("Info", "Id") else False, set=AsyncMock()
    )
    task.script_config = SimpleNamespace(
        get=lambda *args: 1 if args == ("Run", "RunTimesLimit") else False
    )
    task.emulator_manager = None
    task.maaend_root_path = root
    task.maaend_exe_path = root / "MaaEnd.exe"
    task.maaend_instance_name = "AUTO-MAS"
    task.first_run_mode = "Routine"
    task.run_book = {"Routine": False, "Collect": False}
    task.update_failed = False
    task.retryable = True
    task.wait_event = asyncio.Event()
    task.check = AsyncMock(return_value="Pass")
    task.prepare = AsyncMock()
    task._account_switch_method = lambda: "MAAEND"
    task._prepare_auto_collect_routes = Mock()
    task.maaend_process_manager = SimpleNamespace(
        open_process=AsyncMock(), kill=AsyncMock()
    )
    monkeypatch.setattr(
        proxy, "MAAEND_RUN_MOOD_BOOK", {"Routine": "日常", "Collect": "采集"}
    )
    monkeypatch.setattr(proxy, "Config", SimpleNamespace(get=lambda *args: False))
    monkeypatch.setattr(proxy, "System", SimpleNamespace(kill_process=AsyncMock()))
    monkeypatch.setattr(
        proxy,
        "asyncio",
        SimpleNamespace(
            to_thread=asyncio.to_thread,
            sleep=AsyncMock(),
            subprocess=asyncio.subprocess,
            CancelledError=asyncio.CancelledError,
        ),
    )
    return task


@pytest.mark.asyncio
@pytest.mark.parametrize("download", [False, True])
@pytest.mark.parametrize("skip_first", [False, True])
async def test_stage_order_and_no_download_fast_path(
    tmp_path, monkeypatch, download, skip_first
):
    task = make_proxy(monkeypatch, tmp_path)
    if skip_first:
        task.run_book["Routine"] = True
        task.first_run_mode = "Collect"
    order = []

    async def configure(_):
        order.append("configure:" + task.mode)
        task.task_dict = {"任务": {"id": True}}

    async def finish():
        order.append("run:" + task.mode)
        if task.mode == task.first_run_mode and download:
            write_log(tmp_path, "发现新版本: v1.1.0\n开始下载更新: url\n")
        task.cur_user_log.status = "Success!"
        task.cur_user_log.content = ["任务完成\n"]

    async def install(**kwargs):
        assert task.run_book[task.first_run_mode]
        if not skip_first:
            assert not task.run_book["Collect"]
        order.append("update")
        kwargs["on_status"]("更新完成")
        return "v1.1.0"

    monkeypatch.setattr(update, "_run_update_session", install)
    monkeypatch.setattr(
        proxy.MaaEndResourceLoader,
        "get_cached",
        lambda *args, **kwargs: order.append("reload"),
    )
    task.set_maaend = configure
    task._wait_maaend_stage = finish
    await task.main_task()

    expected = ["configure:" + task.first_run_mode, "run:" + task.first_run_mode]
    if download:
        expected += ["update", "reload"]
    if not skip_first:
        expected += ["configure:Collect", "run:Collect"]
    assert order == expected
    assert all(task.run_book.values())
    assert not task.update_failed
    assert len(task.cur_user_item.log_record) == (1 if skip_first else 2) + int(
        download
    )


@pytest.mark.asyncio
async def test_update_failure_preserves_first_stage_and_stops_next(
    tmp_path, monkeypatch
):
    task = make_proxy(monkeypatch, tmp_path)
    configured = []

    async def configure(_):
        configured.append(task.mode)
        task.task_dict = {"任务": {"id": True}}

    async def finish():
        write_log(tmp_path, "开始下载更新: url\n")
        task.cur_user_log.status = "Success!"

    monkeypatch.setattr(
        update,
        "_run_update_session",
        AsyncMock(side_effect=update.MaaEndUpdateError("安装失败")),
    )
    task.set_maaend = configure
    task._wait_maaend_stage = finish
    with pytest.raises(update.MaaEndUpdateError):
        await task.main_task()
    assert configured == ["Routine"]
    assert task.run_book == {"Routine": True, "Collect": False}
    assert task.update_failed
    logs = list(task.cur_user_item.log_record.values())
    assert logs[0].status == "Success!"
    assert logs[1].phase == "Update"
    assert "安装失败" in logs[1].status


@pytest.mark.asyncio
async def test_failed_update_cannot_turn_into_success_in_finalizer(
    tmp_path, monkeypatch
):
    task = make_proxy(monkeypatch, tmp_path)
    task.check_result = "Pass"
    task.update_failed = True
    task.run_book = {"Routine": True, "Collect": True}
    task.maaend_log_monitor = SimpleNamespace(stop=AsyncMock())
    task.script_info.current_index = 0
    task.script_info.user_list = [task.cur_user_item]
    task.stopped_manually = False
    task.kill_managed_process = AsyncMock()
    task.push_log_enabled = False
    task.user_start_time = datetime.now()
    task.cur_user_item.log_record = {
        datetime(2026, 9, 30, 10): LogRecord(
            phase="Routine", content=["任务完成\n"], status="Success!"
        ),
        datetime(2026, 9, 30, 11): LogRecord(
            phase="Update", content=["更新安装失败\n"], status="更新安装失败"
        ),
    }
    config = SimpleNamespace(
        build_history_log_path=lambda **kwargs: (
            tmp_path / kwargs["log_time"].strftime("%H%M%S")
        ),
        save_maaend_log=AsyncMock(),
        merge_statistic_info=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(proxy, "Config", config)
    monkeypatch.setattr(proxy, "is_backend_dev_mode", lambda: False)
    monkeypatch.setattr(proxy, "push_notification", AsyncMock())

    await task.final_task()
    assert task.cur_user_item.status == "异常"
    task.cur_user_config.set.assert_awaited_once_with("Data", "LastProxyStatus", "失败")
    assert [
        call.kwargs["phase_label"] for call in config.save_maaend_log.await_args_list
    ] == ["日常", "更新"]


@pytest.mark.asyncio
async def test_manager_stops_remaining_users_after_update_failure(monkeypatch):
    manager = importlib.import_module("app.task.MaaEnd.manager")

    class ScriptConfig:
        def get(self, *args):
            return "用户"

    class FailedTask:
        def __init__(self, **kwargs):
            self.update_failed = True

    task = manager.MaaEndManager.__new__(manager.MaaEndManager)
    task.check = AsyncMock(return_value="Pass")
    task.prepare = AsyncMock()
    task.task_info = SimpleNamespace(mode="AutoProxy")
    task.script_config = ScriptConfig()
    task.script_info = SimpleNamespace(
        user_list=[
            UserItem(
                user_id="00000000-0000-0000-0000-000000000001", name="一", status="等待"
            ),
            UserItem(
                user_id="00000000-0000-0000-0000-000000000002", name="二", status="等待"
            ),
        ]
    )
    task.user_config = {
        manager.uuid.UUID(user.user_id): ScriptConfig()
        for user in task.script_info.user_list
    }
    task.emulator_manager = None
    task.spawn = AsyncMock()
    task._restore_script_config_from_temp = AsyncMock()
    monkeypatch.setattr(manager, "MaaEndConfig", ScriptConfig)
    monkeypatch.setattr(manager, "AutoProxyTask", FailedTask)
    monkeypatch.setattr(manager, "METHOD_BOOK", {"AutoProxy": FailedTask})

    await task.main_task()
    task.spawn.assert_awaited_once()
    task._restore_script_config_from_temp.assert_awaited_once()
    assert task.script_info.current_index == 0
