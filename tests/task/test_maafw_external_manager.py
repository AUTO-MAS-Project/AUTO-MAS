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
from app.models.config import MaaFWConfig
from app.models.task import ScriptItem
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

    def __init__(self, time_stamp_range, time_format, callback):
        self.time_stamp_range = time_stamp_range
        self.time_format = time_format
        self.callback = callback
        self.start_calls = []
        self.stop_calls = 0
        self.__class__.instances.append(self)

    async def start_monitor_file(self, path, start_time):
        self.start_calls.append((path, start_time))
        if self.callback_lines is not None:
            await self.callback(self.callback_lines, datetime.now())

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
        _FakeSystem.events = []
        _FakeSystem.kill_success = True

    def test_success_writes_config_and_starts_bare_exe(self) -> None:
        asyncio.run(self._test_success_writes_config_and_starts_bare_exe())

    async def _test_success_writes_config_and_starts_bare_exe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            self._make_project(root)
            before = self._snapshot(root / "config")
            manager, runtime, script_uid = await self._make_manager(root)
            _FakeLogMonitor.callback_lines = [
                "2026-08-27 18:00:00.000 任务已全部完成！\n"
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
                "2026-08-27 18:00:01.000 任务已全部完成！\n"
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

    def test_dispatch_branch_is_registered(self) -> None:
        source = Path("app/core/task_manager.py").read_text(encoding="utf-8")
        self.assertIn("elif isinstance(script_config, MaaFWConfig):", source)
        self.assertIn("task_item = MaaFWManager(script_item)", source)

    async def _make_manager(self, root: Path, *, runtime=None, script_uid=None):
        script_uid = script_uid or uuid.uuid4()
        script_config = MaaFWConfig()
        await script_config.update(
            {
                "Info": {"Name": "测试 MaaFW", "Path": str(root)},
                "Selection": {
                    "Controller": json.dumps(["安卓端"], ensure_ascii=False),
                    "Resource": json.dumps(["简中"], ensure_ascii=False),
                    "Tasks": json.dumps(["启动游戏"], ensure_ascii=False),
                },
            }
        )
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

    @staticmethod
    def _make_project(root: Path) -> None:
        (root / "config" / "instances").mkdir(parents=True)
        (root / "project").mkdir()
        (root / "logs").mkdir()
        (root / "MFAAvalonia.dll").write_bytes(b"dll")
        (root / "appsettings.json").write_text("{}", encoding="utf-8")
        (root / "MFAAvalonia.exe").write_bytes(b"exe")
        (root / "project" / "MFAAvalonia.exe").write_bytes(b"compat-exe")
        (root / "other.exe").write_bytes(b"other-exe")
        (root / "interface.json").write_text("{}", encoding="utf-8")
        (root / "config" / "instances" / "default.json").write_text(
            json.dumps({"original": {"value": 1}, "TaskItems": ["old"]}),
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

    def _patched_runtime(self, runtime, manager, sleep):
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
            patch.object(manager_module, "load_interface_model", return_value=_interface())
        )
        stack.enter_context(patch.object(manager_module.asyncio, "sleep", side_effect=sleep))
        return stack


if __name__ == "__main__":
    unittest.main()
