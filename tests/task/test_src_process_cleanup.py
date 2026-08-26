import asyncio
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psutil

from app.models.task import LogRecord
from app.task.SRC.AutoProxy import AutoProxyTask
from app.task.SRC.tools.process import (
    _kill_src_toolkit_processes,
    _scan_src_toolkit_context,
    kill_src_processes,
    kill_src_webui_process,
)


class SrcProcessCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_check_log_ignores_takeover_text_in_traceback(self) -> None:
        task = self._build_auto_proxy_task()
        log_content = [
            "2026-08-22 10:00:00.000 │ INFO │ SRC starts\n",
            "Traceback (most recent call last):\n",
            '  File "task.py", line 1, in run\n',
            "    logger.critical('Request human takeover')\n",
        ]

        await task.check_log(log_content, datetime.now())

        self.assertEqual(task.cur_user_log.status, "SRC 正常运行中")
        self.assertFalse(task.wait_event.is_set())

    async def test_check_log_detects_structured_takeover_log(self) -> None:
        task = self._build_auto_proxy_task()
        log_content = ["2026-08-22 10:00:00.000 │ CRITICAL │ Request human takeover\n"]

        await task.check_log(log_content, datetime.now())

        self.assertEqual(
            task.cur_user_log.status,
            "SRC 无法继续执行任务, 需要用户接管",
        )
        self.assertTrue(task.wait_event.is_set())

    async def test_toolkit_cleanup_keeps_root_executables(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            toolkit_path = src_root / "toolkit"
            toolkit_path.mkdir(parents=True)
            (toolkit_path / "python.exe").touch()
            processes = [
                SimpleNamespace(
                    info={
                        "pid": 123,
                        "name": "updater.exe",
                        "exe": str(src_root / "updater.exe"),
                    }
                ),
                SimpleNamespace(
                    info={
                        "pid": 456,
                        "name": "python.exe",
                        "exe": str(toolkit_path / "python.exe"),
                    }
                ),
            ]

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.process_iter",
                    return_value=processes,
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await _kill_src_toolkit_processes(src_root)

            kill_process_by_pid.assert_awaited_once_with(456)
            self.assertTrue(cleanup_success)

    async def test_unreadable_common_toolkit_process_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            toolkit_path = src_root / "toolkit"
            toolkit_path.mkdir(parents=True)
            (toolkit_path / "python.exe").touch()
            process = SimpleNamespace(
                info={"pid": 456, "name": "python.exe", "exe": None}
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.process_iter",
                    return_value=[process],
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await _kill_src_toolkit_processes(src_root)

            kill_process_by_pid.assert_not_awaited()
            self.assertTrue(cleanup_success)

    async def test_self_process_is_skipped_before_name_matching(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            toolkit_path = src_root / "toolkit"
            toolkit_path.mkdir(parents=True)
            (toolkit_path / "python.exe").touch()
            processes = [
                SimpleNamespace(
                    info={
                        "pid": os.getpid(),
                        "name": "python.exe",
                        "exe": None,
                    }
                ),
                SimpleNamespace(
                    info={
                        "pid": 456,
                        "name": "python.exe",
                        "exe": str(toolkit_path / "python.exe"),
                    }
                ),
            ]

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.process_iter",
                    return_value=processes,
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await _kill_src_toolkit_processes(src_root)

            kill_process_by_pid.assert_awaited_once_with(456)
            self.assertTrue(cleanup_success)

    async def test_webui_cleanup_requires_launch_port_and_src_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )
            toolkit_connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )
            updater_connection = SimpleNamespace(
                pid=789,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[toolkit_connection, updater_connection],
                ) as net_connections,
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                process.return_value.exe.side_effect = [
                    str(src_root / "toolkit" / "python.exe"),
                    str(src_root / "updater.exe"),
                ]
                cleanup_success = await kill_src_webui_process(
                    src_root,
                    src_set_path,
                    webui_port=22267,
                )

            net_connections.assert_called_once_with(kind="tcp")
            kill_process_by_pid.assert_awaited_once_with(123)
            self.assertTrue(cleanup_success)

    async def test_cleanup_steps_run_independently(self) -> None:
        process_manager = SimpleNamespace(
            main_pid=None,
            is_running=AsyncMock(),
            kill=AsyncMock(side_effect=RuntimeError("tracked process failure")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.touch()
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                    return_value=False,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process._kill_src_toolkit_processes",
                    new_callable=AsyncMock,
                    return_value=False,
                ) as kill_toolkit_processes,
                patch(
                    "app.task.SRC.tools.process.kill_src_webui_process",
                    new_callable=AsyncMock,
                    return_value=False,
                ),
                patch("app.task.SRC.tools.process.logger"),
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_exe_path,
                    src_root_path=src_root_path,
                    src_set_path=src_set_path,
                )

        process_manager.kill.assert_awaited_once_with()
        kill_process.assert_awaited_once_with(src_exe_path.resolve())
        self.assertEqual(kill_toolkit_processes.await_count, 2)
        self.assertEqual(
            [args.args[0] for args in kill_toolkit_processes.await_args_list],
            [src_root_path.resolve(), src_root_path.resolve()],
        )
        self.assertFalse(cleanup_success)

    async def test_tracked_process_tree_is_killed_first(self) -> None:
        events: list[str] = []
        process_manager = SimpleNamespace(
            main_pid=123,
            is_running=AsyncMock(return_value=True),
            kill=AsyncMock(side_effect=lambda: events.append("manager")),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.touch()
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    side_effect=lambda *_: events.append("tree") or True,
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                    side_effect=lambda *_: events.append("path") or True,
                ),
                patch(
                    "app.task.SRC.tools.process._kill_src_toolkit_processes",
                    new_callable=AsyncMock,
                    side_effect=lambda *_args, **_kwargs: (
                        events.append("toolkit") or True
                    ),
                ),
                patch(
                    "app.task.SRC.tools.process.kill_src_webui_process",
                    new_callable=AsyncMock,
                    side_effect=lambda *_args, **_kwargs: (
                        events.append("webui") or True
                    ),
                ),
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_exe_path,
                    src_root_path=src_root_path,
                    src_set_path=src_set_path,
                )

        self.assertEqual(
            events,
            ["tree", "path", "toolkit", "manager", "webui", "toolkit"],
        )
        self.assertTrue(cleanup_success)

    async def test_toolkit_scan_is_reused_for_both_cleanup_passes(self) -> None:
        process_manager = SimpleNamespace(
            main_pid=None,
            is_running=AsyncMock(),
            kill=AsyncMock(),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.touch()
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            toolkit_context = _scan_src_toolkit_context(src_root_path)

            with (
                patch(
                    "app.task.SRC.tools.process._scan_src_toolkit_context",
                    return_value=toolkit_context,
                ) as scan_toolkit_context,
                patch(
                    "app.task.SRC.tools.process._kill_src_toolkit_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_toolkit_processes,
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch(
                    "app.task.SRC.tools.process.kill_src_webui_process",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_exe_path,
                    src_root_path=src_root_path,
                    src_set_path=src_set_path,
                )

        scan_toolkit_context.assert_called_once_with(src_root_path.resolve())
        self.assertEqual(kill_toolkit_processes.await_count, 2)
        self.assertIs(
            kill_toolkit_processes.await_args_list[0].kwargs["toolkit_context"],
            toolkit_context,
        )
        self.assertIs(
            kill_toolkit_processes.await_args_list[1].kwargs["toolkit_context"],
            toolkit_context,
        )
        self.assertTrue(cleanup_success)

    async def test_cleanup_timeout_returns_false(self) -> None:
        process_manager = SimpleNamespace(main_pid=None)

        async def stalled_cleanup(*_args, **_kwargs) -> bool:
            await asyncio.sleep(0.1)
            return True

        with (
            patch(
                "app.task.SRC.tools.process._kill_src_processes",
                side_effect=stalled_cleanup,
            ),
            patch(
                "app.task.SRC.tools.process._PROCESS_CLEANUP_TIMEOUT_SECONDS",
                0.01,
            ),
        ):
            cleanup_success = await kill_src_processes(
                process_manager,
                src_exe_path=Path("SRC/src.exe"),
                src_root_path=Path("SRC"),
                src_set_path=Path("SRC/config"),
            )

        self.assertFalse(cleanup_success)

    async def test_invalid_cleanup_path_raises_src_validation_error(self) -> None:
        process_manager = SimpleNamespace(main_pid=None)
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()

            with patch("app.task.SRC.tools.process.logger"):
                with self.assertRaisesRegex(ValueError, "SRC 清理根目录缺少配置特征"):
                    await kill_src_processes(
                        process_manager,
                        src_exe_path=src_root_path / "src.exe",
                        src_root_path=src_root_path,
                        src_set_path=src_root_path / "config",
                    )

    def _build_auto_proxy_task(self) -> AutoProxyTask:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.cur_user_log = LogRecord()
        task.script_info = SimpleNamespace(log="")
        task.script_config = SimpleNamespace(get=lambda *_: 30)
        task.src_process_manager = SimpleNamespace(
            is_running=AsyncMock(return_value=True)
        )
        task.wait_event = asyncio.Event()
        return task


if __name__ == "__main__":
    unittest.main()
