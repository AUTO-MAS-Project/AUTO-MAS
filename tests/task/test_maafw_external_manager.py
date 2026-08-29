import asyncio
import json
import re
import tempfile
import uuid
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import app.core

from app.core.task_manager import TaskInfo
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceInfo, DeviceStatus
from app.models.task import ScriptItem
from app.utils.constants import UTC4
from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWController,
    MaaFWInterface,
    MaaFWOption,
    MaaFWOptionCase,
    MaaFWResource,
    MaaFWTask,
)
from app.task.MaaFW.tools.external.shell import ShellFamily


_ORIGINAL_ASYNCIO_SLEEP = asyncio.sleep


class _RuntimeConfig:
    def __init__(self, script_uid, script_config):
        self.ScriptConfig = {script_uid: script_config}
        self.EmulatorConfig = {}
        self.messages = []
        # 仅供启动准备用到的 Function.* 开关（如 IfSilence），默认全部为假。
        self.function_flags: dict[tuple[str, str], object] = {}
        # 历史记录根目录；_make_manager 会指到测试临时目录内，随之自动清理。
        self.history_path = Path(tempfile.gettempdir()) / "maafw-test-history"

    async def send_websocket_message(self, **message):
        self.messages.append(message)

    def get(self, group, name):
        return self.function_flags.get((group, name), False)

    # ---- 历史记录基础设施：与 app/core/config.py 中同名实现保持一致 ----

    def build_history_log_path(
        self, *, script_name: str, user_name: str, log_time: datetime
    ) -> Path:
        safe_script_name = re.sub(r'[<>:"/\\|?*]', "_", str(script_name or "").strip())
        safe_script_name = safe_script_name.rstrip(" .") or "空白"
        time_suffix = f"-{log_time.strftime('%H-%M-%S')}.log"
        safe_script_name = safe_script_name[: 255 - len(time_suffix)]
        return (
            self.history_path
            / log_time.strftime("%Y-%m-%d")
            / user_name
            / f"{safe_script_name}{time_suffix}"
        )

    async def save_general_log(self, log_path: Path, logs: list, general_result: str):
        data = {"general_result": general_result}
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.with_suffix(".log").write_text("".join(logs), encoding="utf-8")
        log_path.with_suffix(".json").write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )

    async def search_history(self, mode: str, start_date: date, end_date: date) -> dict:
        history_dict: dict[str, dict[str, list[Path]]] = {}
        if not self.history_path.exists():
            return history_dict
        for date_folder in self.history_path.iterdir():
            if not date_folder.is_dir():
                continue
            try:
                folder_date = datetime.strptime(date_folder.name, "%Y-%m-%d").date()
            except ValueError:
                continue
            if not (start_date <= folder_date <= end_date):
                continue
            date_name = folder_date.strftime("%Y-%m-%d")
            bucket = history_dict.setdefault(date_name, {})
            for user_folder in date_folder.iterdir():
                if not user_folder.is_dir():
                    continue
                bucket.setdefault(user_folder.stem, []).extend(
                    user_folder.glob("*.json")
                )
        return history_dict


class _FakeEmulator:
    instances: list = []
    open_should_raise = False
    ld_devices: dict = {}

    def __init__(self, emulator_id):
        self.emulator_id = emulator_id
        self.open_calls: list = []
        self.close_calls: list = []
        self.set_visible_calls: list = []
        self.__class__.instances.append(self)

    async def open(self, index, package_name=""):
        self.open_calls.append(index)
        if self.__class__.open_should_raise:
            raise RuntimeError("模拟器起不来")
        # title 取 MuMu 实例真实标题风格；MuMu AdbDevice.Name 由它派生。
        return DeviceInfo(
            title="MuMu安卓设备",
            status=DeviceStatus.ONLINE,
            adb_address="127.0.0.1:16384",
        )

    async def close(self, index):
        self.close_calls.append(index)

    async def setVisible(self, index, is_visible):
        self.set_visible_calls.append((index, is_visible))

    async def get_device_info(self, index):
        return self.__class__.ld_devices


class _FakeEmulatorConfig:
    def __init__(self, emulator_type: str, path: str):
        self.values = {("Info", "Type"): emulator_type, ("Info", "Path"): path}

    def get(self, group, name):
        return self.values[(group, name)]


class _FakeLdDevice:
    def __init__(self, *, title: str, idx: int, pid: int):
        self.title = title
        self.idx = idx
        self.pid = pid


class _FakeEmulatorManager:
    @staticmethod
    async def get_emulator_instance(emulator_id):
        return _FakeEmulator(emulator_id)


class _FakeProcessManager:
    instances = []
    next_running = True
    fail_open = False
    # 只让第 N 次 open_process 抛错（N 从 0 起），用于「一个用户炸了、队列继续」。
    fail_open_at_index = None

    def __init__(self):
        self.open_calls = []
        self.kill_calls = 0
        self.running = self.next_running
        self.main_pid = 4312
        self.__class__.instances.append(self)

    async def open_process(self, *args, **kwargs):
        self.open_calls.append((args, kwargs))
        if self.fail_open:
            raise RuntimeError("fake open failed")
        if self.__class__.fail_open_at_index is not None and (
            self.__class__.instances.index(self) == self.__class__.fail_open_at_index
        ):
            raise RuntimeError("fake open failed for this user")

    async def is_running(self):
        return self.running

    async def kill(self):
        self.kill_calls += 1
        self.running = False


class _FakeLogMonitor:
    instances = []
    callback_lines = None
    # 多用户：按监视器创建顺序依次取一组日志行，用尽后回退到 callback_lines。
    pending_callback_lines: list = []

    def __init__(self, time_stamp_range, time_format, callback):
        self.time_stamp_range = time_stamp_range
        self.time_format = time_format
        self.callback = callback
        self.start_calls = []
        self.stop_calls = 0
        self.__class__.instances.append(self)

    async def start_monitor_file(self, path, start_time):
        self.start_calls.append((path, start_time))
        if self.__class__.pending_callback_lines:
            lines = self.__class__.pending_callback_lines.pop(0)
        else:
            lines = self.callback_lines
        if lines is not None:
            await self.callback(lines, datetime.now())

    async def stop(self):
        self.stop_calls += 1


class _FakeSystem:
    events = []
    kill_success = True

    @classmethod
    async def kill_process(cls, path):
        cls.events.append(("kill", Path(path)))
        return cls.kill_success


class _FakeNotify:
    plyer_calls: list = []

    @classmethod
    async def push_plyer(cls, title: str, message: str, ticker: str, t: int) -> None:
        cls.plyer_calls.append((title, message, ticker, t))


class _FakeReportPush:
    calls: list = []
    should_raise = False

    @classmethod
    async def push(cls, mode: str, title: str, message: dict) -> None:
        cls.calls.append((mode, title, message))
        if cls.should_raise:
            raise RuntimeError("fake push failed")


def _interface() -> MaaFWInterface:
    return MaaFWInterface(
        interface_version=2,
        name="test-project",
        controller=[MaaFWController(name="安卓端", type="Adb")],
        resource=[MaaFWResource(name="简中")],
        task=[MaaFWTask(name="启动游戏", entry="StartUp")],
    )


class MaaFWExternalManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        _FakeProcessManager.instances = []
        _FakeProcessManager.next_running = True
        _FakeProcessManager.fail_open = False
        _FakeProcessManager.fail_open_at_index = None
        _FakeLogMonitor.instances = []
        _FakeLogMonitor.callback_lines = None
        _FakeLogMonitor.pending_callback_lines = []
        _FakeSystem.events = []
        _FakeSystem.kill_success = True
        _FakeEmulator.instances = []
        _FakeEmulator.open_should_raise = False
        _FakeEmulator.ld_devices = {}
        _FakeNotify.plyer_calls = []
        _FakeReportPush.calls = []
        _FakeReportPush.should_raise = False

    _SUCCESS_LOG = (
        "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
        "2026-08-27 18:00:01.000 任务已全部完成！\n"
    )

    def test_success_launches_shell_with_active_instance_only(self) -> None:
        asyncio.run(self._test_success_launches_shell_with_active_instance_only())

    async def _test_success_launches_shell_with_active_instance_only(self) -> None:
        """外壳只接 --instance，绝不接 --autostart。

        实测（D:/MAS/tmp/m9a-test，非提权 MuMu）：外壳的 --autostart 走
        StartCommandLineAutoRun 直接 StartTask()，跳过 TryReadAdbDeviceFromConfig /
        WaitSoftware，Config.AdbDevice 永不填充，控制器初始化即报 AdbSerial 为空；
        只传 --instance 才会经 WaitSoftware 完成设备恢复并连上。
        自动运行由实例配置的 BeforeTask=StartupSoftwareAndScript 驱动。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            instances = root / "config" / "instances"
            (instances / "adbe33bf.json").write_bytes(
                (instances / "default.json").read_bytes()
            )
            (root / "appsettings.json").write_text(
                json.dumps({"Instances.LastActive": "adbe33bf"}), encoding="utf-8"
            )
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)
            # 真实成功运行里选中任务名必然在日志中出现过（具体格式未知，只保证子串在）
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
            ]

            async def no_sleep(_delay):
                return None

            with self._patched_runtime(runtime, manager, no_sleep):
                await manager.main_task()
                await manager.final_task()

            process = _FakeProcessManager.instances[0]
            self.assertEqual(
                process.open_calls,
                [
                    (
                        (
                            root / "MFAAvalonia.exe",
                            "--instance",
                            "adbe33bf",
                        ),
                        {},
                    )
                ],
            )
            # 回归守护：--autostart 一旦被重新加回来，设备恢复就会被外壳跳过。
            self.assertNotIn("--autostart", process.open_calls[0][0])
            self.assertEqual(manager.process_pid, 4312)
            self.assertEqual(process.kill_calls, 1)
            self.assertEqual(_FakeLogMonitor.instances[0].stop_calls, 1)
            self.assertEqual(runtime.messages, [])
            self.assertEqual(manager.script_info.status, "完成")
            self.assertEqual(manager.script_info.user_list[0].status, "完成")
            self.assertEqual(
                manager.script_info.user_list[0]
                .log_record[next(iter(manager.script_info.user_list[0].log_record))]
                .content,
                _FakeLogMonitor.callback_lines,
            )
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)

    # ---- 问题 1：运行编排让外壳自行「连接设备 → 跑队列」 ----

    def test_runtime_config_uses_startup_software_and_script(self) -> None:
        asyncio.run(self._test_runtime_config_uses_startup_software_and_script())

    async def _test_runtime_config_uses_startup_software_and_script(self) -> None:
        """BeforeTask 必须写成 StartupSoftwareAndScript；SoftwarePath 恒为空串。

        实测（D:/MAS/tmp/m9a-test）：BeforeTask="None" 时 --autostart 触发的
        op=StartTask 在设备选中前即被拒（「未选择连接目标」）；改为
        StartupSoftwareAndScript 后相同参数进入 op=ExecuteTaskQueue 自行连接。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            instance_path = root / "config" / "instances" / "default.json"
            # 用户实例里残留了一个非空的启动软件路径——绝不能透传给外壳，
            # 否则外壳会重复启动模拟器（模拟器归 MAS 的 EmulatorManager 管）。
            stale_base = json.loads(instance_path.read_text(encoding="utf-8"))
            stale_base["SoftwarePath"] = "C:/leidian/LDPlayer9/dnplayer.exe"
            stale_base["BeforeTask"] = "None"
            stale_base["AfterTask"] = "None"
            instance_path.write_text(json.dumps(stale_base), encoding="utf-8")

            manager, runtime, _ = await self._make_manager(root)
            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                manager._write_runtime_config()
                # 必须在 final_task 恢复备份之前读取本轮写入的运行配置。
                written = json.loads(
                    manager.instance_path.read_text(encoding="utf-8")
                )
                await manager.final_task()

            self.assertEqual(written["BeforeTask"], "StartupSoftwareAndScript")
            self.assertEqual(written["SoftwarePath"], "")
            # AfterTask 保持 "None"：本层集中管理外壳/模拟器生命周期，不采用
            # M9A 的 CloseEmulatorAndMFA（会与日志判定、模拟器归属产生竞态）。
            self.assertEqual(written["AfterTask"], "None")
            self.assertEqual(written["InstanceName"], "MAS")

    # ---- 问题 2：运行收尾写入历史记录 ----

    def test_run_writes_searchable_history_record(self) -> None:
        asyncio.run(self._test_run_writes_searchable_history_record())

    async def _test_run_writes_searchable_history_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            today = datetime.now(tz=UTC4).date()
            found = await runtime.search_history(
                "DAILY", today - timedelta(days=1), today + timedelta(days=1)
            )
            jsons = [
                path
                for buckets in found.values()
                for paths in buckets.values()
                for path in paths
            ]
            self.assertEqual(len(jsons), 1, found)
            self.assertIn("用户A", str(jsons[0].parent))
            payload = json.loads(jsons[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["general_result"], "Success!")
            self.assertTrue(jsons[0].with_suffix(".log").is_file())

    def test_history_is_written_once_per_user_with_status(self) -> None:
        asyncio.run(self._test_history_is_written_once_per_user_with_status())

    async def _test_history_is_written_once_per_user_with_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "甲", "tasks": ["启动游戏"]},
                    {"Name": "乙", "tasks": ["启动游戏"]},
                ],
            )
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
                # final_task 幂等：再调一次不得产生重复历史文件。
                await manager.final_task()

            today = datetime.now(tz=UTC4).date()
            found = await runtime.search_history(
                "DAILY", today - timedelta(days=1), today + timedelta(days=1)
            )
            users = {
                user: len(paths)
                for buckets in found.values()
                for user, paths in buckets.items()
            }
            self.assertEqual(users, {"甲": 1, "乙": 1})

    def test_failed_run_history_records_failure_status(self) -> None:
        asyncio.run(self._test_failed_run_history_records_failure_status())

    async def _test_failed_run_history_records_failure_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 19:00:00.000 [WRN] [op=ExecuteTaskQueue] "
                "控制器初始化结果为空\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            today = datetime.now(tz=UTC4).date()
            found = await runtime.search_history(
                "DAILY", today - timedelta(days=1), today + timedelta(days=1)
            )
            payloads = [
                json.loads(path.read_text(encoding="utf-8"))
                for buckets in found.values()
                for paths in buckets.values()
                for path in paths
            ]
            self.assertEqual(len(payloads), 1)
            self.assertIn("控制器初始化失败", payloads[0]["general_result"])

    # ---- 问题 3：运行收尾推送任务报告 ----

    def test_final_task_pushes_run_report_once(self) -> None:
        asyncio.run(self._test_final_task_pushes_run_report_once())

    async def _test_final_task_pushes_run_report_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
                # final_task 可能被多路径重复调用，报告必须幂等。
                await manager.final_task()

            self.assertEqual(len(_FakeReportPush.calls), 1)
            mode, title, message = _FakeReportPush.calls[0]
            self.assertEqual(mode, "代理结果")
            self.assertIn("测试 MaaFW", title)
            self.assertIn("自动代理任务报告", title)
            self.assertEqual(message["completed_count"], 1)
            self.assertEqual(message["uncompleted_count"], 0)
            self.assertIn("用户A", message["result"])
            self.assertEqual(len(_FakeNotify.plyer_calls), 1)
            self.assertIn("已完成！", _FakeNotify.plyer_calls[0][0])

    def test_failed_run_report_counts_uncompleted(self) -> None:
        asyncio.run(self._test_failed_run_report_counts_uncompleted())

    async def _test_failed_run_report_counts_uncompleted(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 19:00:00.000 [WRN] [op=ExecuteTaskQueue] "
                "控制器初始化结果为空\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(len(_FakeReportPush.calls), 1)
            _, _, message = _FakeReportPush.calls[0]
            self.assertEqual(message["completed_count"], 0)
            self.assertEqual(message["uncompleted_count"], 1)

    def test_no_report_before_check_passes(self) -> None:
        asyncio.run(self._test_no_report_before_check_passes())

    async def _test_no_report_before_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            # 取消或崩溃可在 check 通过前触发 final_task；此时无可报告内容。
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.final_task()

            self.assertEqual(_FakeReportPush.calls, [])
            self.assertEqual(_FakeNotify.plyer_calls, [])

    def test_report_failure_does_not_break_final_task(self) -> None:
        asyncio.run(self._test_report_failure_does_not_break_final_task())

    async def _test_report_failure_does_not_break_final_task(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            _FakeReportPush.should_raise = True
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.script_info.status, "完成")
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)
            self.assertTrue(
                any(
                    "推送 MaaFW 任务报告失败" in str(m.get("data", {}))
                    for m in runtime.messages
                )
            )

    # ---- 问题 10：外壳自己的更新必须关掉，更新归 MAS 控制 ----

    def test_shell_self_update_is_disabled_and_restored(self) -> None:
        asyncio.run(self._test_shell_self_update_is_disabled_and_restored())

    async def _test_shell_self_update_is_disabled_and_restored(self) -> None:
        """运行期压住外壳自更新，收尾按备份还原用户原值。

        键名取自靶子真实 config.json。外壳同时更新会与 MAS 的更新端点抢同一批
        文件，且失败时污染判定（真机日志里有「获取资源包下载信息失败：来源=
        Mirror」抛异常那一段）。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            config_json = root / "config" / "config.json"
            original = {
                "EnableCheckVersion": True,
                "EnableAutoUpdateResource": True,
                "EnableAutoUpdateMFA": False,
                "DownloadCDK": "user-cdk",
            }
            config_json.write_text(json.dumps(original), encoding="utf-8")

            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                manager._write_runtime_config()
                written = json.loads(config_json.read_text(encoding="utf-8"))
                await manager.final_task()

            # 运行期：三个更新开关全部压住。
            self.assertFalse(written["EnableCheckVersion"])
            self.assertFalse(written["EnableAutoUpdateResource"])
            self.assertFalse(written["EnableAutoUpdateMFA"])
            # 与更新无关的键原样保留。
            self.assertEqual(written["DownloadCDK"], "user-cdk")
            # 收尾：整个 config/ 按备份还原，用户原值回来了。
            restored = json.loads(config_json.read_text(encoding="utf-8"))
            self.assertEqual(restored, original)

    # ---- 问题 9：外壳判定失败必须立刻收口，不能干等超时 ----

    # 逐字取自 D:\MAS\tmp\m9a-test\logs\log-20260829.log 的真机运行：
    # 启动游戏 跑了 15 分 38 秒后失败，外壳停掉整个队列并输出本行。
    _FAILURE_LOG = (
        "[2026-08-29 16:14:08.000][INF] [cfg=Default][inst=MAS/default]"
        "[src=Monitor][op=MonitorLog] 开始任务：启动游戏\n"
        "[2026-08-29 16:29:47.660][INF] [cfg=Default][inst=MAS/default]"
        "[src=Monitor][op=MonitorLog] 任务运行失败！\n"
    )

    def test_task_failure_alone_does_not_end_the_run(self) -> None:
        """单个任务失败**不得**让 MAS 提前收口。

        队列会不会因此停下来取决于实例配置的 ContinueRunningWhenError——
        M9A 在该项为真时会跳过失败任务继续跑后面的。此前把失败串当终止信号，
        队列还在跑就会被 MAS 判死。
        """

        asyncio.run(self._test_task_failure_alone_does_not_end_the_run())

    async def _test_task_failure_alone_does_not_end_the_run(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            with self._patched_runtime(runtime, manager, self._no_sleep):
                manager._ensure_virtual_user()
                await manager.check_log([self._FAILURE_LOG], datetime.now())

            # 只见失败串、没见排空串 → 不许有终态。
            self.assertIsNone(manager.terminal_kind)

    def test_failure_downgrades_completed_queue_to_failed(self) -> None:
        asyncio.run(self._test_failure_downgrades_completed_queue_to_failed())

    async def _test_failure_downgrades_completed_queue_to_failed(self) -> None:
        """队列跑到排空、但中途有任务失败 → 判 failed 而非 success。

        选中任务都露过面（不是 tasks_missing），只是没全成。沿用本层取舍：
        宁可误报失败也不误报成功。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                self._FAILURE_LOG
                + "[2026-08-29 16:29:48.000][INF] [src=Monitor][op=MonitorLog] "
                "任务已全部完成！\n"
            ]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "failed")
            self.assertEqual(manager.script_info.user_list[0].status, "异常")
            self.assertNotEqual(manager.script_info.status, "完成")

    def test_clean_queue_still_succeeds(self) -> None:
        asyncio.run(self._test_clean_queue_still_succeeds())

    async def _test_clean_queue_still_succeeds(self) -> None:
        """没有失败串时仍判 success——降级逻辑不得误伤正常成功路径。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "success")
            self.assertEqual(manager.script_info.status, "完成")

    # ---- 问题 8：appsettings.json 的实例指针必须还原 ----

    def test_appsettings_instance_pointers_are_restored(self) -> None:
        asyncio.run(self._test_appsettings_instance_pointers_are_restored())

    async def _test_appsettings_instance_pointers_are_restored(self) -> None:
        """备份范围只有 config/，但外壳会改写项目根 appsettings.json 的实例指针。

        MAS 删光 instances/*.json 只留自己那个，外壳退出时把 List / Order 收缩成
        单项、LastActive 指向 MAS 实例。这四键不还原的话，用户的实例集合在外壳
        UI 里会永久变成只剩 MAS 一个。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            app_path = root / "appsettings.json"
            original = {
                "Instances.List": "adbe33bf,7ym1fl9",
                "Instances.Order": "adbe33bf,7ym1fl9",
                "Instances.LastActive": "adbe33bf",
                "Instances.LastActiveName": "用户自己的配置",
                "ShowGui": "未设置",
            }
            app_path.write_text(json.dumps(original), encoding="utf-8")
            (root / "config" / "instances" / "adbe33bf.json").write_bytes(
                (root / "config" / "instances" / "default.json").read_bytes()
            )

            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                # 模拟外壳退出时把实例集合收缩成只剩 MAS 那一个。
                app_path.write_text(
                    json.dumps(
                        {
                            "Instances.List": "adbe33bf",
                            "Instances.Order": "adbe33bf",
                            "Instances.LastActive": "adbe33bf",
                            "Instances.LastActiveName": "MAS",
                            "ShowGui": "未设置",
                            "Window.Left": "120",
                        }
                    ),
                    encoding="utf-8",
                )
                await manager.final_task()

            restored = json.loads(app_path.read_text(encoding="utf-8"))
            for key in (
                "Instances.List",
                "Instances.Order",
                "Instances.LastActive",
                "Instances.LastActiveName",
            ):
                self.assertEqual(restored[key], original[key], key)
            # 与实例指针无关的键不被回滚：外壳运行期的其他改动应当保留。
            self.assertEqual(restored["Window.Left"], "120")

    # ---- 问题 7：日志路径必须按开跑时刻重算（跨零点） ----

    def test_log_path_is_recomputed_per_user_run(self) -> None:
        asyncio.run(self._test_log_path_is_recomputed_per_user_run())

    async def _test_log_path_is_recomputed_per_user_run(self) -> None:
        """队列跨零点后，后一个用户必须监控新日期的日志文件。

        此前 log_path 在 check() 里按当天日期算死一次、整轮复用：零点后外壳写
        log-<新日期>.log，而 LogMonitor 还盯着昨天那个不再增长的文件空转，
        last_log_at 冻结，最终按 RunTimeLimit 误判超时并杀掉正在干活的外壳。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "零点前", "tasks": ["启动游戏"]},
                    {"Name": "零点后", "tasks": ["启动游戏"]},
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            real_datetime = manager_module.datetime
            # 调用序：check() 一次、两个用户各一次。前两次仍是 28 日，
            # 第三次（第二个用户开跑）跨到 29 日。
            calls = {"n": 0}
            current = {"day": date(2026, 8, 28)}

            class _Clock(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    stamp = real_datetime.now(tz)
                    return stamp.replace(
                        year=current["day"].year,
                        month=current["day"].month,
                        day=current["day"].day,
                    )

            original_resolve = MaaFWManager._resolve_log_path

            def _resolve_and_advance(self):
                calls["n"] += 1
                if calls["n"] >= 3:
                    current["day"] = date(2026, 8, 29)
                return original_resolve(self)

            with self._patched_runtime(runtime, manager, self._no_sleep), patch.object(
                manager_module, "datetime", _Clock
            ), patch.object(MaaFWManager, "_resolve_log_path", _resolve_and_advance):
                await manager.main_task()
                await manager.final_task()

            monitored = [str(call[0]) for call in
                         [inst.start_calls[0] for inst in _FakeLogMonitor.instances]]
            self.assertEqual(len(monitored), 2)
            self.assertIn("log-20260828.log", monitored[0])
            self.assertIn("log-20260829.log", monitored[1])

    # ---- 问题 6：单个用户抛异常不得中止剩余队列 ----

    def test_user_exception_does_not_abort_remaining_users(self) -> None:
        asyncio.run(self._test_user_exception_does_not_abort_remaining_users())

    async def _test_user_exception_does_not_abort_remaining_users(self) -> None:
        """第一个用户起进程抛异常，第二个用户仍须照常执行。

        此前用户循环没有 try/except：异常直接穿透 main_task 落进 on_crash，
        剩余用户一个都不跑，还会被 final_task 从「等待」统一改判「异常」——
        与 _run_user 内已有的「单用户失败只跳过该用户」三条出口自相矛盾。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "先炸的用户", "tasks": ["启动游戏"]},
                    {"Name": "后续用户", "tasks": ["启动游戏"]},
                ],
            )
            _FakeProcessManager.fail_open_at_index = 0
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            statuses = {u.name: u.status for u in manager.script_info.user_list}
            self.assertEqual(statuses["先炸的用户"], "异常")
            self.assertEqual(statuses["后续用户"], "完成")
            # 第二个用户确实起过自己的外壳。
            self.assertEqual(len(_FakeProcessManager.instances), 2)
            # 失败用户留下可检索的日志条目，历史记录与任务报告都看得到这次失败。
            failed = next(u for u in manager.script_info.user_list if u.name == "先炸的用户")
            self.assertTrue(failed.log_record)
            self.assertIn(
                "用户运行异常",
                next(iter(failed.log_record.values())).status,
            )
            # 整体判异常，且项目配置照常还原。
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(self._snapshot(root / "config"), before)

    def test_teardown_runs_even_when_user_raises(self) -> None:
        asyncio.run(self._test_teardown_runs_even_when_user_raises())

    async def _test_teardown_runs_even_when_user_raises(self) -> None:
        """异常路径也必须做用户间收尾，不能把上一个用户的外壳留给下一个。

        因此 _teardown_shell_between_users 放在 finally 而不是 except 之后，
        更不能用裸 continue 跳过它。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "先炸的用户", "tasks": ["启动游戏"]},
                    {"Name": "后续用户", "tasks": ["启动游戏"]},
                ],
            )
            _FakeProcessManager.fail_open_at_index = 0
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            # 失败用户的外壳进程也被收尾杀掉过（用户间 teardown 生效）。
            self.assertEqual(_FakeProcessManager.instances[0].kill_calls, 1)

    # ---- 问题 4：没排任务的用户不得拖垮整个脚本 ----

    def test_user_without_tasks_is_skipped_and_others_still_run(self) -> None:
        asyncio.run(self._test_user_without_tasks_is_skipped_and_others_still_run())

    async def _test_user_without_tasks_is_skipped_and_others_still_run(self) -> None:
        """新建用户默认 Status=True 且 TaskSnapshot="{ }"。

        此前 check() 对每个启用用户解析快照、空快照即抛错并整体拒绝运行，
        于是「刚新建一个用户」会让整个脚本连同已配好的用户一起跑不了。
        现在该用户按「跳过」处理，其余用户照常执行。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "已配置", "tasks": ["启动游戏"]},
                    {"Name": "新建用户", "tasks": []},
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.main_task()
                await manager.final_task()

            statuses = {u.name: u.status for u in manager.script_info.user_list}
            self.assertEqual(statuses["已配置"], "完成")
            self.assertEqual(statuses["新建用户"], "跳过")
            self.assertEqual(manager.script_info.status, "完成")
            # 只有配了任务的那个用户真正起过外壳。
            self.assertEqual(len(_FakeProcessManager.instances), 1)

    def test_check_fails_only_when_no_user_has_tasks(self) -> None:
        asyncio.run(self._test_check_fails_only_when_no_user_has_tasks())

    async def _test_check_fails_only_when_no_user_has_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root, users=[{"Name": "空用户", "tasks": []}]
            )
            with self._patched_runtime(runtime, manager, self._no_sleep):
                result = await manager.check()
            self.assertIn("没有任何启用用户排入任务", result)

    # ---- 问题 5：用户选的任务选项必须真的写进外壳配置 ----

    def test_user_task_options_reach_instance_config(self) -> None:
        asyncio.run(self._test_user_task_options_reach_instance_config())

    async def _test_user_task_options_reach_instance_config(self) -> None:
        """此前只构造 TaskSelection(name=...)，映射层因而回退到 interface 默认值，
        把用户选的选项静默换成每项第 0 个 case。现在用户值必须原样抵达实例配置。
        """

        interface = MaaFWInterface(
            interface_version=2,
            name="test-project",
            controller=[MaaFWController(name="安卓端", type="Adb")],
            resource=[MaaFWResource(name="简中")],
            task=[
                MaaFWTask(name="启动游戏", entry="StartUp", option=["服务器"]),
            ],
            option={
                "服务器": MaaFWOption(
                    type="select",
                    cases=[
                        MaaFWOptionCase(name="官服"),
                        MaaFWOptionCase(name="B 服"),
                    ],
                )
            },
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {
                        "Name": "用户A",
                        "tasks": ["启动游戏"],
                        "taskOptions": {"启动游戏": {"服务器": "B 服"}},
                    }
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(
                runtime, manager, self._no_sleep, interface=interface
            ):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                await manager._run_user(0, manager.runnable_user_uids[0])
                # 必须在 final_task 还原备份之前读取本轮写入的实例配置。
                written = json.loads(manager.instance_path.read_text(encoding="utf-8"))
                await manager.final_task()

            option = written["TaskItems"][0]["option"]
            self.assertEqual(option, [{"name": "服务器", "index": 1}])

    def test_non_mfa_is_explicitly_unsupported(self) -> None:
        asyncio.run(self._test_non_mfa_is_explicitly_unsupported())

    async def _test_non_mfa_is_explicitly_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            with patch.object(manager_module, "Config", runtime), patch.object(manager_module, "detect_shell_family", return_value=ShellFamily.MXU):
                result = await manager.check()
            self.assertIn("暂不支持", result)
            self.assertIn("MFAAvalonia", result)
            self.assertFalse(runtime.ScriptConfig[next(iter(runtime.ScriptConfig))].is_locked)

    def test_abandon_exit_and_timeout_have_expected_priority(self) -> None:
        asyncio.run(self._test_abandon_exit_and_timeout_have_expected_priority())

    async def _test_abandon_exit_and_timeout_have_expected_priority(self) -> None:
        for mode in ("abandon", "exit", "timeout"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir) / "project"
                self._make_project(root)
                before = self._snapshot(root / "config")
                manager, runtime, _ = await self._make_manager(root)

                if mode == "abandon":
                    _FakeProcessManager.next_running = True
                    _FakeLogMonitor.callback_lines = [
                        "2026-08-27 18:00:00.000 已放弃本次任务\n"
                    ]
                elif mode == "exit":
                    _FakeProcessManager.next_running = False
                    _FakeLogMonitor.callback_lines = None
                else:
                    _FakeProcessManager.next_running = True
                    _FakeLogMonitor.callback_lines = []

                    async def timeout_sleep(delay):
                        if delay == 5:
                            manager.last_log_at = datetime.now() - timedelta(hours=2)

                async def no_sleep(_delay):
                    return None

                sleep = timeout_sleep if mode == "timeout" else no_sleep
                with self._patched_runtime(runtime, manager, sleep):
                    await manager.main_task()
                    await manager.final_task()
                self.assertEqual(manager.terminal_kind, {
                    "abandon": "abandoned",
                    "exit": "exit",
                    "timeout": "timeout",
                }[mode])
                self.assertEqual(manager.script_info.status, "异常")
                self.assertEqual(self._snapshot(root / "config"), before)

    def test_completion_wins_over_abandon_and_process_exit(self) -> None:
        asyncio.run(self._test_completion_wins_over_abandon_and_process_exit())

    async def _test_completion_wins_over_abandon_and_process_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 已放弃本次任务\n"
                "2026-08-27 18:00:00.500 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.terminal_kind, "success")
            self.assertEqual(manager.script_info.status, "完成")

    def test_controller_failure_overrides_completion_string(self) -> None:
        asyncio.run(self._test_controller_failure_overrides_completion_string())

    async def _test_controller_failure_overrides_completion_string(self) -> None:
        """外壳排空队列时照样输出完成串——控制器初始化失败必须压过它。

        fixture 取自真实运行日志 D:/MAS/tmp/slice-e2e/logs/log-20260827.log：
        控制器初始化失败 21 毫秒后即出现「任务已全部完成！」，紧随其后的耗时行
        为 (用时 0h 0m 0s)，选中的任务从未执行。若判成功即为假成功。
        """

        real_log = (
            "2026-08-27 19:08:22.666 [ERR] [cfg=Default][inst=MAS/default]"
            "[src=Worker][op=ExecuteTaskQueue] 初始化控制器失败："
            "message=连接模拟器时发生错误！, reason=The value cannot be an "
            "empty string.（Parameter 'info.AdbSerial')\n"
            "2026-08-27 19:08:22.687 [INF] [cfg=Default][inst=MAS/default]"
            "[src=Monitor][op=MonitorLog] 任务已全部完成！\n"
            "(用时 0h 0m 0s)\n"
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [real_log]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "controller_failed")
            self.assertEqual(manager.script_info.status, "异常")
            # 失败路径同样必须还原项目配置
            self.assertEqual(self._snapshot(root / "config"), before)

    def test_controller_failure_can_overturn_an_earlier_success(self) -> None:
        asyncio.run(self._test_controller_failure_can_overturn_an_earlier_success())

    async def _test_controller_failure_can_overturn_an_earlier_success(self) -> None:
        """完成串先到、控制器失败后到时，仍须推翻已提交的成功结论。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 19:00:00.000 任务已全部完成！\n",
                "2026-08-27 19:00:01.000 [ERR] [op=ExecuteTaskQueue] "
                "初始化控制器失败：message=连接模拟器时发生错误！\n",
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "controller_failed")
            self.assertEqual(manager.script_info.status, "异常")

    def test_empty_controller_result_also_counts_as_failure(self) -> None:
        asyncio.run(self._test_empty_controller_result_also_counts_as_failure())

    async def _test_empty_controller_result_also_counts_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 19:00:00.000 [WRN] [op=ExecuteTaskQueue] "
                "控制器初始化结果为空\n"
                "2026-08-27 19:00:01.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.terminal_kind, "controller_failed")

    def test_benign_error_lines_do_not_trigger_failure(self) -> None:
        asyncio.run(self._test_benign_error_lines_do_not_trigger_failure())

    async def _test_benign_error_lines_do_not_trigger_failure(self) -> None:
        """同一份真实日志里的噪音错误不得误判为失败。

        「获取设备唯一标识失败」出现 24 次、「跨平台数据解密失败」14 次，
        均与运行结果无关；只有带 op=ExecuteTaskQueue 的控制器标记才有判别性。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 19:00:00.000 [ERR] 获取设备唯一标识失败：xxx\n"
                "2026-08-27 19:00:00.500 [WRN] 跨平台数据解密失败：yyy\n"
                "2026-08-27 19:00:01.000 [WRN] 公告文件夹不存在：zzz\n"
                "2026-08-27 19:00:01.500 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 19:00:02.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.terminal_kind, "success")
            self.assertEqual(manager.script_info.status, "完成")

    def test_exception_and_cancel_restore_config_and_await_cleanup(self) -> None:
        asyncio.run(self._test_exception_and_cancel_restore_config_and_await_cleanup())

    async def _test_exception_and_cancel_restore_config_and_await_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(root)
            _FakeProcessManager.fail_open = True
            with self._patched_runtime(runtime, manager, self._no_sleep):
                # 起进程失败的异常现在被收敛到该用户身上，不再穿透 main_task
                # 中止整个队列（多用户隔离见
                # test_user_exception_does_not_abort_remaining_users）。
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.script_info.user_list[0].status, "异常")
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertEqual(_FakeProcessManager.instances[0].kill_calls, 1)
            self.assertEqual(_FakeLogMonitor.instances[0].stop_calls, 1)
            self.assertFalse(runtime.ScriptConfig[next(iter(runtime.ScriptConfig))].is_locked)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(root)
            blocking = asyncio.Event()

            async def sleep_until_cancel(delay):
                if delay == 5:
                    await blocking.wait()

            with self._patched_runtime(runtime, manager, sleep_until_cancel):
                task = asyncio.create_task(manager.main_task())
                await _ORIGINAL_ASYNCIO_SLEEP(0)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertEqual(_FakeProcessManager.instances[0].kill_calls, 1)
            self.assertEqual(_FakeLogMonitor.instances[0].stop_calls, 1)
            self.assertFalse(runtime.ScriptConfig[next(iter(runtime.ScriptConfig))].is_locked)

    def test_residual_backup_is_restored_before_new_backup(self) -> None:
        asyncio.run(self._test_residual_backup_is_restored_before_new_backup())

    async def _test_residual_backup_is_restored_before_new_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            original = self._snapshot(root / "config")
            first, runtime, script_uid = await self._make_manager(root)
            with patch.object(manager_module, "Config", runtime), patch.object(manager_module, "detect_shell_family", return_value=ShellFamily.MFAAVALONIA), patch.object(manager_module, "load_interface_model", return_value=_interface()):
                self.assertEqual(await first.check(), "Pass")
                first._backup_project_config()
            (root / "config" / "new-by-crash.json").write_text("{}", encoding="utf-8")

            second, _, _ = await self._make_manager(root, runtime=runtime, script_uid=script_uid)
            with self._patched_runtime(runtime, second, self._no_sleep):
                await second.check()
                await second.prepare()
            self.assertFalse((root / "config" / "new-by-crash.json").exists())
            self.assertEqual(self._snapshot(second.backup_path), original)
            await second.final_task()
            self.assertEqual(self._snapshot(root / "config"), original)

    def test_residual_process_is_killed_before_backup_restore(self) -> None:
        asyncio.run(self._test_residual_process_is_killed_before_backup_restore())

    async def _test_residual_process_is_killed_before_backup_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            first, runtime, script_uid = await self._make_manager(root)
            with self._patched_runtime(runtime, first, self._no_sleep):
                self.assertEqual(await first.check(), "Pass")
                first._backup_project_config()

            second, _, _ = await self._make_manager(
                root, runtime=runtime, script_uid=script_uid
            )
            original_restore = second._restore_backup_from_state

            def record_restore():
                _FakeSystem.events.append(("restore", second.config_dir))
                return original_restore()

            with self._patched_runtime(runtime, second, self._no_sleep):
                with patch.object(
                    second, "_restore_backup_from_state", side_effect=record_restore
                ):
                    await second.check()
                    await second.prepare()

            self.assertEqual(_FakeSystem.events[0][0], "kill")
            self.assertEqual(_FakeSystem.events[0][1], root / "MFAAvalonia.exe")
            self.assertEqual(
                [event[0] for event in _FakeSystem.events[:2]], ["kill", "restore"]
            )
            await second.final_task()

    def test_unpublished_config_tmp_is_ignored_without_touching_live_config(self) -> None:
        asyncio.run(self._test_unpublished_config_tmp_is_ignored_without_touching_live_config())

    async def _test_unpublished_config_tmp_is_ignored_without_touching_live_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)
            manager.state_dir.mkdir(parents=True)
            (manager.state_dir / "config.tmp" / "copied-before-crash.json").parent.mkdir()
            (manager.state_dir / "config.tmp" / "copied-before-crash.json").write_text(
                "{}", encoding="utf-8"
            )

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()

            self.assertFalse((manager.state_dir / "config.tmp").exists())
            self.assertTrue(manager.backup_path.is_dir())
            self.assertEqual(self._snapshot(manager.backup_path), before)
            await manager.final_task()
            self.assertEqual(self._snapshot(root / "config"), before)

    def test_residual_kill_failure_preserves_backup_and_live_config(self) -> None:
        asyncio.run(
            self._test_residual_kill_failure_preserves_backup_and_live_config()
        )

    async def _test_residual_kill_failure_preserves_backup_and_live_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            first, runtime, script_uid = await self._make_manager(root)
            with self._patched_runtime(runtime, first, self._no_sleep):
                self.assertEqual(await first.check(), "Pass")
                first._backup_project_config()

            crash_marker = root / "config" / "written-by-running-shell.json"
            crash_marker.write_text("{}", encoding="utf-8")
            second, _, _ = await self._make_manager(
                root, runtime=runtime, script_uid=script_uid
            )
            _FakeSystem.kill_success = False
            with self._patched_runtime(runtime, second, self._no_sleep):
                self.assertEqual(await second.check(), "Pass")
                with self.assertRaisesRegex(
                    RuntimeError, "残留外壳无法确认已结束"
                ):
                    await second.prepare()
                await second.final_task()

            self.assertTrue(crash_marker.exists())
            self.assertTrue(second.manifest_path.is_file())
            self.assertTrue(second.backup_path.is_dir())
            self.assertIn("已保留 MaaFW 配置备份", second.cleanup_error or "")

    def test_missing_device_identifier_is_rejected_before_launch(self) -> None:
        asyncio.run(self._test_missing_device_identifier_is_rejected_before_launch())

    async def _test_missing_device_identifier_is_rejected_before_launch(self) -> None:
        """Adb 控制器缺设备标识：启动前就拒绝，不起进程、不动配置、不留备份。

        对应实测假成功——MAS 写入的实例配置没有 AdbDevice / Connect.Address，
        外壳连接必失败却仍排空队列输出「任务已全部完成！」。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root, with_device=False)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertIn("未配置模拟器设备", manager.check_result)
            self.assertEqual(manager.script_info.status, "异常")
            # 启动前拒绝：没有任何外壳进程 / 日志监控被创建
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(_FakeLogMonitor.instances, [])
            self.assertEqual(_FakeSystem.events, [])
            # 拒绝路径不改动项目配置、不残留备份、不留锁
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)
            self.assertEqual(len(runtime.messages), 1)
            self.assertIn(
                "未配置模拟器设备", runtime.messages[0]["data"]["Error"]
            )

    def test_unconfigured_stale_absolute_adb_path_is_rejected(self) -> None:
        asyncio.run(self._test_unconfigured_stale_absolute_adb_path_is_rejected())

    async def _test_unconfigured_stale_absolute_adb_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            instance_path = root / "config" / "instances" / "default.json"
            instance = json.loads(instance_path.read_text(encoding="utf-8"))
            missing_adb = root / "removed-ldplayer" / "adb.exe"
            instance["AdbDevice"]["AdbPath"] = missing_adb.as_posix()
            instance_path.write_text(json.dumps(instance), encoding="utf-8")
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertIn("ADB 程序不存在", manager.check_result)
            self.assertIn("请在 MAS 中选择当前模拟器", manager.check_result)
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(_FakeEmulator.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)

    def test_empty_task_selection_is_rejected(self) -> None:
        asyncio.run(self._test_empty_task_selection_is_rejected())

    async def _test_empty_task_selection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root, tasks=[])

            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertNotEqual(manager.check_result, "Pass")
            # 唯一的启用用户没排任务 → 整脚本无事可做，仍然拒绝。
            # 文案由「task 不能为空」改为可操作的提示：空快照本身不再是错误，
            # 只有「全部启用用户都没排任务」才判失败（多用户场景见
            # test_user_without_tasks_is_skipped_and_others_still_run）。
            self.assertIn("没有任何启用用户排入任务", manager.check_result)
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)

    def test_completion_requires_selected_tasks_to_appear(self) -> None:
        asyncio.run(self._test_completion_requires_selected_tasks_to_appear())

    async def _test_completion_requires_selected_tasks_to_appear(self) -> None:
        """完成串出现时，选中任务必须在日志里露过面才判成功。"""

        cases = {
            "absent": (
                ["2026-08-27 18:00:01.000 任务已全部完成！\n"],
                "tasks_missing",
                "异常",
            ),
            "present": (
                [
                    "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
                    "2026-08-27 18:00:01.000 任务已全部完成！\n"
                ],
                "success",
                "完成",
            ),
        }
        for name, (lines, terminal, status) in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir) / "project"
                self._make_project(root)
                before = self._snapshot(root / "config")
                manager, runtime, _ = await self._make_manager(root)
                _FakeLogMonitor.callback_lines = lines
                with self._patched_runtime(runtime, manager, self._no_sleep):
                    await manager.main_task()
                    await manager.final_task()
                self.assertEqual(manager.terminal_kind, terminal)
                self.assertEqual(manager.script_info.status, status)
                self.assertEqual(self._snapshot(root / "config"), before)

    def test_completion_fails_when_only_some_selected_tasks_appear(self) -> None:
        asyncio.run(self._test_completion_fails_when_only_some_selected_tasks_appear())

    async def _test_completion_fails_when_only_some_selected_tasks_appear(self) -> None:
        """选中多个任务、只有一部分出现在日志里 → 不判成功。

        场景取自实测：选中「日常-喝咖啡」在整份日志出现 0 次，真正跑的只有内务
        任务，完成串却存在。
        """

        two_task_interface = MaaFWInterface(
            interface_version=2,
            name="test-project",
            controller=[MaaFWController(name="安卓端", type="Adb")],
            resource=[MaaFWResource(name="简中")],
            task=[
                MaaFWTask(name="启动游戏", entry="StartUp"),
                MaaFWTask(name="日常-喝咖啡", entry="Daily"),
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(
                root, tasks=["启动游戏", "日常-喝咖啡"]
            )
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
            ]
            with self._patched_runtime(
                runtime, manager, self._no_sleep, interface=two_task_interface
            ):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "tasks_missing")
            self.assertIn("日常-喝咖啡", manager.current_log.status)
            self.assertNotIn("启动游戏", manager.current_log.status)
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(self._snapshot(root / "config"), before)

    def test_dispatch_branch_is_registered(self) -> None:
        source = Path("app/core/task_manager.py").read_text(encoding="utf-8")
        self.assertIn("elif isinstance(script_config, MaaFWConfig):", source)
        self.assertIn("task_item = MaaFWManager(script_item)", source)

    # ---- 用户层迁移：用户遍历 / 字段回退 ----

    def test_iterates_every_enabled_user(self) -> None:
        asyncio.run(self._test_iterates_every_enabled_user())

    async def _test_iterates_every_enabled_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "甲", "tasks": ["启动游戏"]},
                    {"Name": "乙", "tasks": ["启动游戏"]},
                ],
            )
            _FakeLogMonitor.pending_callback_lines = [
                [self._SUCCESS_LOG],
                [self._SUCCESS_LOG],
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                [u.name for u in manager.script_info.user_list], ["甲", "乙"]
            )
            self.assertEqual(
                [u.status for u in manager.script_info.user_list], ["完成", "完成"]
            )
            self.assertEqual(manager.script_info.status, "完成")
            # 每个用户一份外壳进程 + 日志监控；用户间外壳先结束再起下一个。
            self.assertEqual(len(_FakeProcessManager.instances), 2)
            self.assertEqual(_FakeProcessManager.instances[0].kill_calls, 1)
            self.assertEqual(_FakeLogMonitor.instances[0].stop_calls, 1)
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())

    def test_disabled_and_expired_users_are_filtered(self) -> None:
        asyncio.run(self._test_disabled_and_expired_users_are_filtered())

    async def _test_disabled_and_expired_users_are_filtered(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "启用", "tasks": ["启动游戏"]},
                    {"Name": "停用", "tasks": ["启动游戏"], "Status": False},
                    {"Name": "到期", "tasks": ["启动游戏"], "RemainedDay": 0},
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                [u.name for u in manager.script_info.user_list], ["启用"]
            )
            self.assertEqual(manager.script_info.user_list[0].status, "完成")

    def test_no_runnable_user_is_explicit_error(self) -> None:
        asyncio.run(self._test_no_runnable_user_is_explicit_error())

    async def _test_no_runnable_user_is_explicit_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(
                root,
                users=[{"Name": "停用", "tasks": ["启动游戏"], "Status": False}],
            )
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertIn("没有可运行的用户", manager.check_result)
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)
            self.assertEqual(len(runtime.messages), 1)
            self.assertIn("没有可运行的用户", runtime.messages[0]["data"]["Error"])

    def test_user_controller_falls_back_to_script_default(self) -> None:
        asyncio.run(self._test_user_controller_falls_back_to_script_default())

    async def _test_user_controller_falls_back_to_script_default(self) -> None:
        # 用户级 Info.Controller 留空 → 取脚本级默认；用户级填了则以用户级为准。
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(
                root, users=[{"Name": "甲", "tasks": ["启动游戏"], "Controller": "安卓端"}]
            )
            # 抹掉脚本级默认，仅靠用户级 Info.Controller
            await runtime.ScriptConfig[script_uid].update({"Info": {"Controller": ""}})
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.script_info.user_list[0].status, "完成")

    def test_missing_controller_on_both_levels_is_rejected(self) -> None:
        asyncio.run(self._test_missing_controller_on_both_levels_is_rejected())

    async def _test_missing_controller_on_both_levels_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(
                root, users=[{"Name": "甲", "tasks": ["启动游戏"]}]
            )
            await runtime.ScriptConfig[script_uid].update({"Info": {"Controller": ""}})
            with self._patched_runtime(runtime, manager, self._no_sleep):
                result = await manager.check()
            self.assertIn("未确定 MaaFW controller", result)

    def test_user_failure_does_not_abort_the_queue(self) -> None:
        asyncio.run(self._test_user_failure_does_not_abort_the_queue())

    async def _test_user_failure_does_not_abort_the_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(
                root,
                users=[
                    {"Name": "先失败", "tasks": ["启动游戏"]},
                    {"Name": "后成功", "tasks": ["启动游戏"]},
                ],
            )
            _FakeLogMonitor.pending_callback_lines = [
                ["2026-08-27 18:00:00.000 已放弃本次任务\n"],
                [self._SUCCESS_LOG],
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                [u.status for u in manager.script_info.user_list], ["异常", "完成"]
            )
            self.assertEqual(manager.script_info.status, "异常")
            self.assertEqual(self._snapshot(root / "config"), before)

    # ---- 周期性跳过 ----

    @staticmethod
    def _daily_period_key() -> str:
        return datetime.now(tz=UTC4).strftime("%Y-%m-%d")

    def test_period_once_task_skipped_when_done_this_period(self) -> None:
        asyncio.run(self._test_period_once_task_skipped_when_done_this_period())

    async def _test_period_once_task_skipped_when_done_this_period(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, _ = await self._make_manager(
                root,
                run_config={"DailyOnceTasks": json.dumps(["启动游戏"], ensure_ascii=False)},
                users=[
                    {
                        "Name": "甲",
                        "tasks": ["启动游戏"],
                        "PeriodTaskRecords": {"daily": {"启动游戏": self._daily_period_key()}},
                    }
                ],
            )
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.script_info.user_list[0].status, "跳过")
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)

    def test_period_task_runs_when_record_is_stale(self) -> None:
        asyncio.run(self._test_period_task_runs_when_record_is_stale())

    async def _test_period_task_runs_when_record_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                run_config={"DailyOnceTasks": json.dumps(["启动游戏"], ensure_ascii=False)},
                users=[
                    {
                        "Name": "甲",
                        "tasks": ["启动游戏"],
                        "PeriodTaskRecords": {"daily": {"启动游戏": "2000-01-01"}},
                    }
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.script_info.user_list[0].status, "完成")
            self.assertEqual(len(_FakeProcessManager.instances), 1)

    def test_success_records_period_task_completion(self) -> None:
        asyncio.run(self._test_success_records_period_task_completion())

    async def _test_success_records_period_task_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(
                root,
                run_config={
                    "WeeklyOnceTasks": json.dumps(["启动游戏"], ensure_ascii=False)
                },
                users=[{"Name": "甲", "tasks": ["启动游戏"]}],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.script_info.user_list[0].status, "完成")
            uid = next(iter(manager.user_config.keys()))
            records = json.loads(
                manager.user_config[uid].get("Data", "PeriodTaskRecords")
            )
            self.assertIn("启动游戏", records.get("weekly", {}))

    def test_partial_period_skip_keeps_remaining_task(self) -> None:
        asyncio.run(self._test_partial_period_skip_keeps_remaining_task())

    async def _test_partial_period_skip_keeps_remaining_task(self) -> None:
        two_task_interface = MaaFWInterface(
            interface_version=2,
            name="test-project",
            controller=[MaaFWController(name="安卓端", type="Adb")],
            resource=[MaaFWResource(name="简中")],
            task=[
                MaaFWTask(name="启动游戏", entry="StartUp"),
                MaaFWTask(name="日常", entry="Daily"),
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(
                root,
                tasks=["启动游戏", "日常"],
                run_config={"DailyOnceTasks": json.dumps(["日常"], ensure_ascii=False)},
                users=[
                    {
                        "Name": "甲",
                        "tasks": ["启动游戏", "日常"],
                        "PeriodTaskRecords": {"daily": {"日常": self._daily_period_key()}},
                    }
                ],
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(
                runtime, manager, self._no_sleep, interface=two_task_interface
            ):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                [s.name for s in manager.task_selections], ["启动游戏"]
            )
            self.assertEqual(manager.script_info.user_list[0].status, "完成")

    # ---- 运行前启动准备：Adb 起模拟器 / Win32 起 PC 游戏 ----

    async def _configure_emulator(
        self,
        script_config,
        *,
        runtime=None,
        index: str = "0",
        emulator_type: str = "mumu",
        path: str = "C:/MuMuPlayer-12.0/shell/MuMuManager.exe",
    ) -> str:
        """给脚本配置写入一个通过校验的模拟器 Id/Index，返回该 Id。"""

        emu_uid = uuid.uuid4()
        MaaFWConfig.related_config["EmulatorConfig"] = {emu_uid: object()}
        self.addCleanup(MaaFWConfig.related_config.pop, "EmulatorConfig", None)
        await script_config.update(
            {"Emulator": {"Id": str(emu_uid), "Index": index}}
        )
        if runtime is not None:
            runtime.EmulatorConfig[emu_uid] = _FakeEmulatorConfig(emulator_type, path)
        self.assertEqual(script_config.get("Emulator", "Id"), str(emu_uid))
        return str(emu_uid)

    def test_configured_emulator_is_started_before_shell(self) -> None:
        asyncio.run(self._test_configured_emulator_is_started_before_shell())

    async def _test_configured_emulator_is_started_before_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            await self._configure_emulator(
                runtime.ScriptConfig[next(iter(runtime.ScriptConfig))], runtime=runtime
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(len(_FakeEmulator.instances), 1)
            self.assertEqual(_FakeEmulator.instances[0].open_calls, ["0"])
            # 外壳确实起了，且模拟器在其之前就绪
            self.assertEqual(len(_FakeProcessManager.instances), 1)
            self.assertEqual(manager.script_info.user_list[0].status, "完成")
            # 收尾关闭模拟器
            self.assertEqual(_FakeEmulator.instances[0].close_calls, ["0"])

    def test_mumu_device_config_overrides_stale_instance_base(self) -> None:
        asyncio.run(self._test_mumu_device_config_overrides_stale_instance_base())

    async def _test_mumu_device_config_overrides_stale_instance_base(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            instance_path = root / "config" / "instances" / "default.json"
            stale_base = json.loads(instance_path.read_text(encoding="utf-8"))
            stale_base["AdbDevice"]["AdbPath"] = "C:/leidian/LDPlayer9/adb.exe"
            instance_path.write_text(json.dumps(stale_base), encoding="utf-8")

            manager, runtime, script_uid = await self._make_manager(root)
            await self._configure_emulator(
                runtime.ScriptConfig[script_uid],
                runtime=runtime,
                index="3",
                emulator_type="mumu",
                path="C:/Netease/MuMuPlayer-12.0/shell/MuMuManager.exe",
            )

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                self.assertIsNone(await manager._prepare_emulator())
                manager._write_runtime_config()
                written = json.loads(manager.instance_path.read_text(encoding="utf-8"))
                await manager.final_task()

            # 外壳的「连接目标」取自 Connect.Address，只写 AdbDevice 不足以选中设备。
            self.assertEqual(written["Connect.Address"], "127.0.0.1:16384")

            device = written["AdbDevice"]
            # Name 取 MuMu 实例真实标题（_FakeEmulator.open 返回 "MuMu安卓设备"），
            # 与 _build_ldplayer_config 一致，不再硬编码 "MuMu模拟器"。
            self.assertEqual(device["Name"], "MuMu安卓设备")
            self.assertEqual(
                device["AdbPath"], "C:/Netease/MuMuPlayer-12.0/shell/adb.exe"
            )
            self.assertEqual(device["AdbSerial"], "127.0.0.1:16384")
            self.assertEqual(
                json.loads(device["Config"]),
                {
                    "extras": {
                        "mumu": {
                            "enable": True,
                            "index": 3,
                            "path": "C:/Netease/MuMuPlayer-12.0",
                        }
                    }
                },
            )

    def test_ldplayer_device_config_uses_registered_emulator(self) -> None:
        asyncio.run(self._test_ldplayer_device_config_uses_registered_emulator())

    async def _test_ldplayer_device_config_uses_registered_emulator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            emulator_id = await self._configure_emulator(
                runtime.ScriptConfig[script_uid],
                runtime=runtime,
                index="2",
                emulator_type="ldplayer",
                path="C:/leidian/LDPlayer14/ldconsole.exe",
            )
            fake_emulator = _FakeEmulator(emulator_id)
            _FakeEmulator.ld_devices = {
                "2": _FakeLdDevice(title="雷电14", idx=2, pid=2468)
            }

            with patch.object(manager_module, "Config", runtime):
                device = await manager._build_adb_device_config(
                    DeviceInfo(
                        title="fake",
                        status=DeviceStatus.ONLINE,
                        adb_address="emulator-5558",
                    ),
                    emulator_id,
                    "2",
                    fake_emulator,
                )

            self.assertIsNotNone(device)
            self.assertEqual(device["Name"], "雷电14")
            self.assertEqual(device["AdbPath"], "C:/leidian/LDPlayer14/adb.exe")
            self.assertEqual(device["AdbSerial"], "emulator-5558")
            self.assertEqual(
                json.loads(device["Config"]),
                {
                    "extras": {
                        "ld": {
                            "enable": True,
                            "index": 2,
                            "path": "C:/leidian/LDPlayer14",
                            "pid": 2468,
                        }
                    }
                },
            )

    _MUMU_PATH = Path("C:/Netease/MuMuPlayer-12.0/shell/MuMuManager.exe")

    def test_mumu_device_config_name_uses_emulator_title(self) -> None:
        asyncio.run(self._test_mumu_device_config_name_uses_emulator_title())

    async def _test_mumu_device_config_name_uses_emulator_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, _, _ = await self._make_manager(root)

            device = manager._build_mumu_config(
                DeviceInfo(
                    title="MuMu安卓设备-1",
                    status=DeviceStatus.ONLINE,
                    adb_address="127.0.0.1:16416",
                ),
                self._MUMU_PATH,
                "1",
            )

            # Name 取实例真实标题，而非硬编码 "MuMu模拟器"。
            self.assertEqual(device["Name"], "MuMu安卓设备-1")
            self.assertEqual(device["AdbSerial"], "127.0.0.1:16416")

    def test_mumu_device_config_name_falls_back_to_adb_address_when_title_blank(
        self,
    ) -> None:
        asyncio.run(
            self._test_mumu_device_config_name_falls_back_to_adb_address_when_title_blank()
        )

    async def _test_mumu_device_config_name_falls_back_to_adb_address_when_title_blank(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, _, _ = await self._make_manager(root)

            device = manager._build_mumu_config(
                DeviceInfo(
                    title="   ",
                    status=DeviceStatus.ONLINE,
                    adb_address="127.0.0.1:16384",
                ),
                self._MUMU_PATH,
                "0",
            )

            # 标题为空白时不退回硬编码 "MuMu模拟器"（与雷电分支不一致），改用 ADB 地址兜底。
            self.assertEqual(device["Name"], "127.0.0.1:16384")

    def test_mumu_device_config_name_falls_back_to_indexed_name_when_address_unknown(
        self,
    ) -> None:
        asyncio.run(
            self._test_mumu_device_config_name_falls_back_to_indexed_name_when_address_unknown()
        )

    async def _test_mumu_device_config_name_falls_back_to_indexed_name_when_address_unknown(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, _, _ = await self._make_manager(root)

            device = manager._build_mumu_config(
                DeviceInfo(
                    title="",
                    status=DeviceStatus.ONLINE,
                    adb_address="Unknown",
                ),
                self._MUMU_PATH,
                "3",
            )

            # 标题与地址都拿不到时，退到带多开号的名字（仍不等于裸 "MuMu模拟器"）。
            self.assertEqual(device["Name"], "MuMu模拟器-3")

    def test_ldplayer_device_config_name_ignores_emulator_info_title(self) -> None:
        asyncio.run(self._test_ldplayer_device_config_name_ignores_emulator_info_title())

    async def _test_ldplayer_device_config_name_ignores_emulator_info_title(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            emulator_id = await self._configure_emulator(
                runtime.ScriptConfig[script_uid],
                runtime=runtime,
                index="2",
                emulator_type="ldplayer",
                path="C:/leidian/LDPlayer14/ldconsole.exe",
            )
            fake_emulator = _FakeEmulator(emulator_id)
            _FakeEmulator.ld_devices = {
                "2": _FakeLdDevice(title="雷电模拟器-2", idx=2, pid=999)
            }

            with patch.object(manager_module, "Config", runtime):
                device = await manager._build_adb_device_config(
                    # 传入一个与雷电真实标题不同的 emulator_info.title，
                    # 雷电分支必须仍取 ld_player_device.title，回归保护。
                    DeviceInfo(
                        title="MuMu安卓设备",
                        status=DeviceStatus.ONLINE,
                        adb_address="emulator-5558",
                    ),
                    emulator_id,
                    "2",
                    fake_emulator,
                )

            self.assertEqual(device["Name"], "雷电模拟器-2")

    def test_unconfigured_emulator_preserves_instance_adb_device(self) -> None:
        asyncio.run(self._test_unconfigured_emulator_preserves_instance_adb_device())

    async def _test_unconfigured_emulator_preserves_instance_adb_device(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                manager._write_runtime_config()
                written = json.loads(manager.instance_path.read_text(encoding="utf-8"))
                await manager.final_task()

            self.assertEqual(written["AdbDevice"], self._DEFAULT_INSTANCE["AdbDevice"])
            # 未登记模拟器时不得凭空写入连接目标，保持透传语义。
            self.assertNotIn("Connect.Address", written)

    def test_unknown_adb_address_does_not_write_connect_address(self) -> None:
        asyncio.run(self._test_unknown_adb_address_does_not_write_connect_address())

    async def _test_unknown_adb_address_does_not_write_connect_address(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            await self._configure_emulator(
                runtime.ScriptConfig[script_uid],
                runtime=runtime,
                index="3",
                emulator_type="mumu",
                path="C:/Netease/MuMuPlayer-12.0/shell/MuMuManager.exe",
            )

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                self.assertIsNone(await manager._prepare_emulator())
                # 模拟器管理器拿不到地址时会返回哨兵值 "Unknown"（见 utils/emulator）。
                manager.emulator_info = DeviceInfo(
                    title="MuMu安卓设备",
                    status=DeviceStatus.ONLINE,
                    adb_address="Unknown",
                )
                manager._write_runtime_config()
                written = json.loads(manager.instance_path.read_text(encoding="utf-8"))
                await manager.final_task()

            self.assertNotIn("Connect.Address", written)
            # 设备本身仍按 MAS 登记生成（AdbDevice 在 _prepare_emulator 期间已按
            # _FakeEmulator.open 的真实标题构建），只是不写连接目标。
            self.assertEqual(written["AdbDevice"]["Name"], "MuMu安卓设备")

    def test_device_build_failure_preserves_instance_adb_device(self) -> None:
        asyncio.run(self._test_device_build_failure_preserves_instance_adb_device())

    async def _test_device_build_failure_preserves_instance_adb_device(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            # 选择值有效且模拟器能启动，但运行时模拟器配置缺失，强制 builder 回退。
            await self._configure_emulator(runtime.ScriptConfig[script_uid])

            with self._patched_runtime(runtime, manager, self._no_sleep):
                self.assertEqual(await manager.check(), "Pass")
                await manager.prepare()
                self.assertIsNone(await manager._prepare_emulator())
                manager._write_runtime_config()
                written = json.loads(manager.instance_path.read_text(encoding="utf-8"))
                await manager.final_task()

            self.assertEqual(written["AdbDevice"], self._DEFAULT_INSTANCE["AdbDevice"])

    def test_unconfigured_emulator_never_touches_emulator_manager(self) -> None:
        asyncio.run(self._test_unconfigured_emulator_never_touches_emulator_manager())

    async def _test_unconfigured_emulator_never_touches_emulator_manager(self) -> None:
        # 未配置 MAS 模拟器 → 沿用活动实例已有设备标识，不与 EmulatorManager 交互。
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, _ = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(_FakeEmulator.instances, [])
            self.assertFalse(manager.emulator_opened)
            self.assertEqual(manager.script_info.user_list[0].status, "完成")

    def test_emulator_launch_failure_skips_shell_and_restores_config(self) -> None:
        asyncio.run(
            self._test_emulator_launch_failure_skips_shell_and_restores_config()
        )

    async def _test_emulator_launch_failure_skips_shell_and_restores_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)
            await self._configure_emulator(
                runtime.ScriptConfig[script_uid], runtime=runtime
            )
            _FakeEmulator.open_should_raise = True
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "launch_failed")
            self.assertIn(
                "模拟器启动失败",
                manager.script_info.user_list[0]
                .log_record[
                    next(iter(manager.script_info.user_list[0].log_record))
                ]
                .status,
            )
            self.assertEqual(manager.script_info.user_list[0].status, "异常")
            self.assertEqual(manager.script_info.status, "异常")
            # 启动准备失败：外壳与日志监控绝不创建
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(_FakeLogMonitor.instances, [])
            # 失败路径同样清理模拟器、还原项目配置、解锁
            self.assertEqual(_FakeEmulator.instances[0].close_calls, ["0"])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)

    def test_emulator_started_once_per_user_and_closed_between_users(self) -> None:
        asyncio.run(
            self._test_emulator_started_once_per_user_and_closed_between_users()
        )

    async def _test_emulator_started_once_per_user_and_closed_between_users(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(
                root,
                users=[
                    {"Name": "甲", "tasks": ["启动游戏"]},
                    {"Name": "乙", "tasks": ["启动游戏"]},
                ],
            )
            await self._configure_emulator(runtime.ScriptConfig[script_uid])
            _FakeLogMonitor.pending_callback_lines = [
                [self._SUCCESS_LOG],
                [self._SUCCESS_LOG],
            ]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                [u.status for u in manager.script_info.user_list], ["完成", "完成"]
            )
            # 复用同一个 EmulatorManager 实例；每个用户各 open 一次，用户间 close。
            self.assertEqual(len(_FakeEmulator.instances), 1)
            self.assertEqual(_FakeEmulator.instances[0].open_calls, ["0", "0"])
            self.assertEqual(_FakeEmulator.instances[0].close_calls, ["0", "0"])

    def test_silent_mode_hides_emulator(self) -> None:
        asyncio.run(self._test_silent_mode_hides_emulator())

    async def _test_silent_mode_hides_emulator(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            await self._configure_emulator(runtime.ScriptConfig[script_uid])
            runtime.function_flags[("Function", "IfSilence")] = True
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            with self._patched_runtime(runtime, manager, self._no_sleep):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(
                _FakeEmulator.instances[0].set_visible_calls, [("0", False)]
            )

    def test_unsupported_controller_type_is_rejected_early(self) -> None:
        asyncio.run(self._test_unsupported_controller_type_is_rejected_early())

    async def _test_unsupported_controller_type_is_rejected_early(self) -> None:
        """映射层未登记该 controller 枚举时，check() 必须在起进程之前就拒绝。

        否则 _prepare_launch_for_user 会先把游戏／模拟器起起来，随后
        _write_runtime_config 才抛 UnknownControllerTypeError——白起一次进程。
        本用例不给 resolve_controller_code 打桩，走真实的映射层登记表。
        """

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)

            with self._patched_runtime(
                runtime, manager, self._no_sleep, interface=self._win32_interface()
            ):
                result = await manager.check()

            self.assertIn("暂不支持", result)
            self.assertIn("Win32", result)
            # 未起任何进程、未动项目配置、未留状态目录
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())

    def test_registered_controller_type_is_not_rejected(self) -> None:
        """守护上一条不是恒真：Adb 已登记，不得被这条拒绝误伤。"""

        from app.task.MaaFW.tools.external import resolve_controller_code

        self.assertEqual(resolve_controller_code("Adb"), 2)
        self.assertIsNone(resolve_controller_code("Win32"))

    @staticmethod
    def _win32_interface() -> MaaFWInterface:
        return MaaFWInterface(
            interface_version=2,
            name="test-project",
            controller=[MaaFWController(name="安卓端", type="Win32")],
            resource=[MaaFWResource(name="简中")],
            task=[MaaFWTask(name="启动游戏", entry="StartUp")],
        )

    def _patch_game_lifecycle(self, *, owned, attach_found=True):
        stack = ExitStack()
        launched: list = []
        closed: list = []

        async def fake_launch(spec, *, preexisting=None):
            launched.append((spec, preexisting))
            return owned

        # 外壳的实例配置映射（tools/external，受保护）目前只登记 Adb 的
        # CurrentController 枚举，Win32 取值在 reference 的全部实例样本中都不存在，
        # 映射层按设计 fail-closed。check() 因此会提前拒绝 Win32（见
        # test_unsupported_controller_type_is_rejected_early）。
        #
        # 本组用例要验的是「启动准备与收尾」本身，故显式声明「假设该枚举日后被确认」：
        # 给 resolve_controller_code 打桩返回一个占位值，并把写实例配置置空。
        # 这是声明前提，不是绕过判断——拒绝行为另有专门用例守护。
        stack.enter_context(
            patch.object(manager_module, "resolve_controller_code", lambda t: 2)
        )
        stack.enter_context(
            patch.object(manager_module.MaaFWManager, "_write_runtime_config", lambda self: None)
        )
        stack.enter_context(
            patch.object(manager_module, "launch_game", side_effect=fake_launch)
        )
        stack.enter_context(
            patch.object(
                manager_module, "snapshot_matching_processes", return_value=set()
            )
        )
        stack.enter_context(
            patch.object(
                manager_module,
                "close_owned_game",
                side_effect=lambda proc: closed.append(proc),
            )
        )
        stack.enter_context(
            patch.object(
                manager_module,
                "find_client_process",
                return_value=object() if attach_found else None,
            )
        )
        return stack, launched, closed

    def test_win32_game_launched_before_shell_and_closed_on_finish(self) -> None:
        asyncio.run(
            self._test_win32_game_launched_before_shell_and_closed_on_finish()
        )

    async def _test_win32_game_launched_before_shell_and_closed_on_finish(
        self,
    ) -> None:
        from app.task.MaaFW.tools.controller.game_lifecycle import (
            MaaFWOwnedGameProcess,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            game_exe = Path(temp_dir) / "game.exe"
            game_exe.write_bytes(b"exe")
            manager, runtime, script_uid = await self._make_manager(root)
            await runtime.ScriptConfig[script_uid].update(
                {
                    "Game": {
                        "LaunchMode": "DirectExe",
                        "LaunchPath": str(game_exe),
                        "CloseOnFinish": True,
                    }
                }
            )
            owned = MaaFWOwnedGameProcess(pid=4321, create_time=1.0)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            game_stack, launched, closed = self._patch_game_lifecycle(owned=owned)
            with game_stack, self._patched_runtime(
                runtime, manager, self._no_sleep, interface=self._win32_interface()
            ):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(len(launched), 1)
            self.assertEqual(launched[0][0].mode, "DirectExe")
            self.assertEqual(len(_FakeProcessManager.instances), 1)
            self.assertEqual(manager.script_info.user_list[0].status, "完成")
            self.assertEqual(closed, [owned])

    def test_win32_game_not_closed_when_close_on_finish_false(self) -> None:
        asyncio.run(
            self._test_win32_game_not_closed_when_close_on_finish_false()
        )

    async def _test_win32_game_not_closed_when_close_on_finish_false(self) -> None:
        from app.task.MaaFW.tools.controller.game_lifecycle import (
            MaaFWOwnedGameProcess,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            game_exe = Path(temp_dir) / "game.exe"
            game_exe.write_bytes(b"exe")
            manager, runtime, script_uid = await self._make_manager(root)
            await runtime.ScriptConfig[script_uid].update(
                {
                    "Game": {
                        "LaunchMode": "DirectExe",
                        "LaunchPath": str(game_exe),
                        "CloseOnFinish": False,
                    }
                }
            )
            owned = MaaFWOwnedGameProcess(pid=4321, create_time=1.0)
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            game_stack, launched, closed = self._patch_game_lifecycle(owned=owned)
            with game_stack, self._patched_runtime(
                runtime, manager, self._no_sleep, interface=self._win32_interface()
            ):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(len(launched), 1)
            self.assertEqual(closed, [])
            self.assertEqual(manager.script_info.user_list[0].status, "完成")

    def test_win32_invalid_game_config_skips_shell(self) -> None:
        asyncio.run(self._test_win32_invalid_game_config_skips_shell())

    async def _test_win32_invalid_game_config_skips_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)
            # DirectExe 但 LaunchPath 指向不存在的文件 → validate 抛错
            await runtime.ScriptConfig[script_uid].update(
                {"Game": {"LaunchMode": "DirectExe", "LaunchPath": "Z:/nope.exe"}}
            )
            # 同上：声明「假设 Win32 枚举日后被确认」，专注验证启动准备的失败路径。
            with patch.object(
                manager_module, "resolve_controller_code", lambda t: 2
            ), self._patched_runtime(
                runtime, manager, self._no_sleep, interface=self._win32_interface()
            ):
                await manager.main_task()
                await manager.final_task()

            self.assertEqual(manager.terminal_kind, "launch_failed")
            self.assertIn(
                "PC 游戏启动配置无效",
                manager.script_info.user_list[0]
                .log_record[
                    next(iter(manager.script_info.user_list[0].log_record))
                ]
                .status,
            )
            self.assertEqual(manager.script_info.user_list[0].status, "异常")
            self.assertEqual(_FakeProcessManager.instances, [])
            self.assertEqual(self._snapshot(root / "config"), before)
            self.assertFalse(manager.state_dir.exists())
            self.assertFalse(runtime.ScriptConfig[script_uid].is_locked)

    def test_win32_attach_only_requires_running_client(self) -> None:
        asyncio.run(self._test_win32_attach_only_requires_running_client())

    async def _test_win32_attach_only_requires_running_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            manager, runtime, script_uid = await self._make_manager(root)
            await runtime.ScriptConfig[script_uid].update(
                {
                    "Game": {
                        "LaunchMode": "AttachOnly",
                        "ProcessName": "game.exe",
                    }
                }
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            # 客户端未运行 → 启动准备失败，不进外壳
            miss_stack, _, _ = self._patch_game_lifecycle(
                owned=None, attach_found=False
            )
            with miss_stack, self._patched_runtime(
                runtime, manager, self._no_sleep, interface=self._win32_interface()
            ):
                await manager.main_task()
                await manager.final_task()
            self.assertEqual(manager.terminal_kind, "launch_failed")
            self.assertEqual(_FakeProcessManager.instances, [])

            # 客户端已在运行 → AttachOnly 放行，正常进外壳
            _FakeProcessManager.instances = []
            _FakeLogMonitor.instances = []
            manager2, runtime2, script_uid2 = await self._make_manager(root)
            await runtime2.ScriptConfig[script_uid2].update(
                {"Game": {"LaunchMode": "AttachOnly", "ProcessName": "game.exe"}}
            )
            _FakeLogMonitor.callback_lines = [self._SUCCESS_LOG]
            hit_stack, launched, closed = self._patch_game_lifecycle(
                owned=None, attach_found=True
            )
            with hit_stack, self._patched_runtime(
                runtime2, manager2, self._no_sleep, interface=self._win32_interface()
            ):
                await manager2.main_task()
                await manager2.final_task()
            self.assertEqual(manager2.script_info.user_list[0].status, "完成")
            self.assertEqual(launched, [])  # AttachOnly 从不启动进程
            self.assertEqual(closed, [])  # 也从不关闭非自己启动的进程

    async def _make_manager(
        self,
        root: Path,
        *,
        runtime=None,
        script_uid=None,
        tasks=None,
        users=None,
        run_config=None,
    ):
        script_uid = script_uid or uuid.uuid4()
        script_config = MaaFWConfig()
        # 用户层迁移后：controller / resource 走 Info.*，运行范围走用户 TaskSnapshot。
        await script_config.update(
            {
                "Info": {
                    "Name": "测试 MaaFW",
                    "Path": str(root),
                    "Controller": "安卓端",
                    "Resource": "简中",
                },
            }
        )
        if run_config:
            await script_config.update({"Run": dict(run_config)})
        selected_tasks = ["启动游戏"] if tasks is None else list(tasks)
        user_specs = users if users is not None else [{"Name": "用户A", "tasks": selected_tasks}]
        for spec in user_specs:
            _, user_cfg = await script_config.UserData.add(MaaFWUserConfig)
            spec_tasks = spec.get("tasks", selected_tasks)
            snapshot = {
                "taskOrder": list(spec_tasks),
                "taskChecked": {name: True for name in spec_tasks},
                "taskOptions": spec.get("taskOptions", {}),
            }
            user_update = {
                "Info": {
                    "Name": spec.get("Name", "用户A"),
                    "Status": spec.get("Status", True),
                    "RemainedDay": spec.get("RemainedDay", -1),
                    "Controller": spec.get("Controller", ""),
                    "Resource": spec.get("Resource", ""),
                },
                "Task": {
                    "SelectedPreset": spec.get("SelectedPreset", ""),
                    "TaskSnapshot": json.dumps(snapshot, ensure_ascii=False),
                },
            }
            if "PeriodTaskRecords" in spec:
                user_update["Data"] = {
                    "PeriodTaskRecords": json.dumps(
                        spec["PeriodTaskRecords"], ensure_ascii=False
                    )
                }
            await user_cfg.update(user_update)
        runtime = runtime or _RuntimeConfig(script_uid, script_config)
        runtime.ScriptConfig[script_uid] = script_config
        # 历史记录写进测试项目的临时目录内，随 TemporaryDirectory 自动清理。
        runtime.history_path = root.parent / "history"
        task_info = TaskInfo(
            mode="AutoProxy",
            task_id="task-id",
            queue_id=None,
            script_id=str(script_uid),
            user_id=None,
        )
        script_item = ScriptItem(script_id=str(script_uid), name="测试 MaaFW", status="运行")
        task_info.script_list = [script_item]
        manager = MaaFWManager(script_item)
        state_root = root.parent / "mas-data"
        manager.state_dir = state_root / str(script_uid) / "MaaFWExternal"
        manager.backup_path = manager.state_dir / "config"
        manager.manifest_path = manager.state_dir / "manifest.json"
        return manager, runtime, script_uid

    # 一个可运行的 MFA 项目：其 instances/default.json 里已有用户此前在外壳侧
    # 连接过一次模拟器留下的设备标识（AdbDevice）。传 with_device=False 构造缺
    # 设备标识的项目，用于验证启动前校验。
    _DEFAULT_INSTANCE = {
        "original": {"value": 1},
        "TaskItems": ["old"],
        "AdbDevice": {"AdbPath": "adb", "AdbSerial": "127.0.0.1:16384"},
    }

    @classmethod
    def _make_project(cls, root: Path, *, with_device: bool = True) -> None:
        (root / "config" / "instances").mkdir(parents=True)
        (root / "project").mkdir()
        (root / "logs").mkdir()
        (root / "MFAAvalonia.dll").write_bytes(b"dll")
        (root / "appsettings.json").write_text("{}", encoding="utf-8")
        (root / "MFAAvalonia.exe").write_bytes(b"exe")
        (root / "project" / "MFAAvalonia.exe").write_bytes(b"compat-exe")
        (root / "other.exe").write_bytes(b"other-exe")
        (root / "interface.json").write_text("{}", encoding="utf-8")
        instance = dict(cls._DEFAULT_INSTANCE)
        if not with_device:
            instance.pop("AdbDevice")
        (root / "config" / "instances" / "default.json").write_text(
            json.dumps(instance),
            encoding="utf-8",
        )
        (root / "config" / "instances" / "other.json").write_text("{}", encoding="utf-8")
        (root / "config" / "nested.json").write_text("{\"nested\": true}", encoding="utf-8")
        (root / "config" / "config.json").write_text(
            json.dumps({"ColorTheme": "Blue", "AutoHide": False}), encoding="utf-8"
        )

    @staticmethod
    def _snapshot(root: Path) -> dict[str, bytes]:
        if not root.exists():
            return {}
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    @staticmethod
    async def _no_sleep(_delay):
        return None

    def _patched_runtime(self, runtime, manager, sleep, *, interface=None):
        stack = ExitStack()
        stack.enter_context(patch.object(manager_module, "Config", runtime))
        stack.enter_context(patch.object(manager_module, "ProcessManager", _FakeProcessManager))
        stack.enter_context(patch.object(manager_module, "LogMonitor", _FakeLogMonitor))
        stack.enter_context(
            patch.object(
                manager_module,
                "System",
                _FakeSystem,
            )
        )
        stack.enter_context(patch.object(manager_module, "Notify", _FakeNotify))
        stack.enter_context(
            patch.object(manager_module, "push_notification", _FakeReportPush.push)
        )
        stack.enter_context(
            patch.object(manager_module, "EmulatorManager", _FakeEmulatorManager)
        )
        stack.enter_context(
            patch.object(
                manager_module,
                "detect_shell_family",
                return_value=ShellFamily.MFAAVALONIA,
            )
        )
        stack.enter_context(
            patch.object(
                manager_module,
                "load_interface_model",
                return_value=interface if interface is not None else _interface(),
            )
        )
        stack.enter_context(patch.object(manager_module.asyncio, "sleep", side_effect=sleep))
        return stack


class MaaFWAdbCheckUsesActiveInstanceTest(unittest.TestCase):
    """启动前 Adb 设备校验必须读 MAS 实际写入的那个实例文件。

    此前该处硬编码 default.json，与 _write_runtime_config 的写入目标不一致：
    对只有 <随机id>.json 的项目（M9A 即如此）会误拒；反之 default.json 有设备
    而活动实例没有时，也可能误放行。
    """

    def test_device_check_reads_active_instance_not_default(self) -> None:
        from app.task.MaaFW.manager import (
            _instance_has_adb_device,
            _read_json_object,
            _resolve_active_instance_path,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            instances = root / "config" / "instances"
            instances.mkdir(parents=True)
            # 活动实例带设备标识；default.json 故意留空
            (instances / "adbe33bf.json").write_text(
                json.dumps({"AdbDevice": {"AdbSerial": "emulator-5554"}}),
                encoding="utf-8",
            )
            (instances / "default.json").write_text(
                json.dumps({"AdbDevice": None}), encoding="utf-8"
            )
            (root / "appsettings.json").write_text(
                json.dumps({"Instances.LastActive": "adbe33bf"}), encoding="utf-8"
            )

            resolved = _resolve_active_instance_path(instances, root)
            self.assertEqual(resolved.name, "adbe33bf.json")
            self.assertTrue(
                _instance_has_adb_device(_read_json_object(resolved, label="t"))
            )
            # 读错文件就会得到相反结论，用它证明这条断言不是恒真
            self.assertFalse(
                _instance_has_adb_device(
                    _read_json_object(instances / "default.json", label="t")
                )
            )

    def test_guard_rejects_mas_written_connect_address(self) -> None:
        """MAS 自己写的 Connect.Address 不得骗过 MAS 自己的启动前守卫。

        该键在参考包的真实实例样本里都不存在，是 MAS 写进去的；此前它被当作合法
        设备标识，于是用户从未在外壳侧连过设备时，第二次运行会被上一轮的残留键
        放行，直到控制器初始化失败才暴露。守卫要的是「用户真的连过一次」的证据。
        """

        from app.task.MaaFW.manager import _instance_has_adb_device

        self.assertFalse(_instance_has_adb_device({"Connect.Address": "127.0.0.1:16384"}))
        self.assertFalse(
            _instance_has_adb_device({"Connect": {"Address": "127.0.0.1:16384"}})
        )
        self.assertTrue(
            _instance_has_adb_device({"AdbDevice": {"AdbSerial": "emulator-5554"}})
        )
        self.assertFalse(_instance_has_adb_device({"AdbDevice": {"AdbSerial": "  "}}))


class MaaFWActiveInstancePathTest(unittest.TestCase):
    """_resolve_active_instance_path：按 appsettings.json 定位活动实例，缺则回退。"""

    def _project(self, tmp: Path, *, appsettings=None, instance_names=("default",)):
        instances = tmp / "config" / "instances"
        instances.mkdir(parents=True)
        for name in instance_names:
            (instances / f"{name}.json").write_text("{}", encoding="utf-8")
        if appsettings is not None:
            (tmp / "appsettings.json").write_text(
                appsettings
                if isinstance(appsettings, str)
                else json.dumps(appsettings),
                encoding="utf-8",
            )
        return instances

    def test_missing_appsettings_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(root, appsettings=None)
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "default.json",
            )

    def test_empty_appsettings_falls_back_to_default(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(root, appsettings={})
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "default.json",
            )

    def test_flat_last_active_points_to_id_named_instance(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(
                root,
                appsettings={"Instances.LastActive": "adbe33bf"},
                instance_names=("adbe33bf",),
            )
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "adbe33bf.json",
            )

    def test_nested_instances_object_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(
                root,
                appsettings={"Instances": {"LastActive": "abc123"}},
                instance_names=("abc123",),
            )
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "abc123.json",
            )

    def test_last_active_without_matching_file_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(
                root, appsettings={"Instances.LastActive": "ghost"}
            )
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "default.json",
            )

    def test_malformed_appsettings_falls_back(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(root, appsettings="{not json")
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "default.json",
            )

    def test_last_active_with_path_separator_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            instances = self._project(
                root, appsettings={"Instances.LastActive": "../../evil"}
            )
            self.assertEqual(
                manager_module._resolve_active_instance_path(instances, root),
                instances / "default.json",
            )


class MaaFWCheckInstanceLocationTest(unittest.TestCase):
    """check() 把 self.instance_path 定位到活动实例，而非硬编码 default.json。"""

    async def _run_check(self, root: Path):
        manager, runtime, _ = await MaaFWExternalManagerTest()._make_manager(root)
        with (
            patch.object(manager_module, "Config", runtime),
            patch.object(
                manager_module, "detect_shell_family", return_value=ShellFamily.MFAAVALONIA
            ),
            patch.object(
                manager_module, "load_interface_model", return_value=_interface()
            ),
        ):
            result = await manager.check()
        return manager, result

    def test_locates_id_named_active_instance(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir) / "project"
                MaaFWExternalManagerTest._make_project(root)
                instances = root / "config" / "instances"
                # 活动实例按 ID 命名；default.json 仍在（携带设备标识，供受保护的
                # 启动前 Adb 校验读取），但运行配置必须写到活动实例。
                (instances / "adbe33bf.json").write_text(
                    (instances / "default.json").read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                (root / "appsettings.json").write_text(
                    json.dumps({"Instances.LastActive": "adbe33bf"}), encoding="utf-8"
                )
                manager, result = await self._run_check(root)
                self.assertEqual(result, "Pass")
                self.assertEqual(manager.instance_path, instances / "adbe33bf.json")

        asyncio.run(scenario())

    def test_falls_back_to_default_when_appsettings_is_empty(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir) / "project"
                MaaFWExternalManagerTest._make_project(root)
                manager, result = await self._run_check(root)
                self.assertEqual(result, "Pass")
                self.assertEqual(
                    manager.instance_path,
                    root / "config" / "instances" / "default.json",
                )

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
