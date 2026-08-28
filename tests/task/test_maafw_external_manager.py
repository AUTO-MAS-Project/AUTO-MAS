import asyncio
import json
import tempfile
import uuid
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import app.core

from app.core.task_manager import TaskInfo
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.task import ScriptItem
from app.utils.constants import UTC4
from app.task.MaaFW import manager as manager_module
from app.task.MaaFW.manager import MaaFWManager
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    MaaFWController,
    MaaFWInterface,
    MaaFWResource,
    MaaFWTask,
)
from app.task.MaaFW.tools.external.shell import ShellFamily


_ORIGINAL_ASYNCIO_SLEEP = asyncio.sleep


class _RuntimeConfig:
    def __init__(self, script_uid, script_config):
        self.ScriptConfig = {script_uid: script_config}
        self.messages = []

    async def send_websocket_message(self, **message):
        self.messages.append(message)


class _FakeProcessManager:
    instances = []
    next_running = True
    fail_open = False

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
        _FakeLogMonitor.instances = []
        _FakeLogMonitor.callback_lines = None
        _FakeLogMonitor.pending_callback_lines = []
        _FakeSystem.events = []
        _FakeSystem.kill_success = True

    _SUCCESS_LOG = (
        "2026-08-27 18:00:00.000 [INF] [inst=MAS/default] 启动游戏\n"
        "2026-08-27 18:00:01.000 任务已全部完成！\n"
    )

    def test_success_writes_config_and_starts_bare_exe(self) -> None:
        asyncio.run(self._test_success_writes_config_and_starts_bare_exe())

    async def _test_success_writes_config_and_starts_bare_exe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
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
            self.assertEqual(process.open_calls, [((root / "MFAAvalonia.exe",), {})])
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
                with self.assertRaises(RuntimeError):
                    await manager.main_task()
                await manager.final_task()
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
            self.assertIn("不能为空", manager.check_result)
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
                "taskOptions": {},
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
