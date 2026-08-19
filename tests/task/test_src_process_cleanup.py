import asyncio
import shutil
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, call, patch

import psutil

from app.task.SRC.AutoProxy import AutoProxyTask
from app.task.SRC.ScriptConfig import ScriptConfigTask
from app.task.SRC.manager import SrcManager
from app.task.SRC.tools.process import (
    _kill_src_root_processes,
    kill_src_processes,
    kill_src_webui_process,
    read_src_process_state,
    SrcProcessState,
    write_src_process_state,
)
from app.task.SRC.tools.config import (
    is_src_config_available,
    read_src_config_snapshot_state,
    read_src_installation_id,
    recover_src_user_config,
    save_src_user_config,
    promote_src_config_update,
    stage_src_config_update,
    write_src_config_snapshot_state,
)
from app.utils.io import read_file, write_file


class SrcProcessCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_src_config_rejects_malformed_deploy_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir)
            (config_path / "src.json").write_text("{}", encoding="utf-8")
            (config_path / "deploy.yaml").write_text(
                "Run: [unterminated", encoding="utf-8"
            )

            self.assertFalse(is_src_config_available(config_path))

    async def test_process_state_preserves_launch_port(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "Temp.process.json"
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()

            write_src_process_state(
                state_path,
                script_id="script-id",
                src_root_path=src_root_path,
                webui_port=22267,
            )

            process_state = read_src_process_state(state_path)
            self.assertIsNotNone(process_state)
            assert process_state is not None
            self.assertEqual(process_state.script_id, "script-id")
            self.assertEqual(process_state.src_root_path, src_root_path.resolve())
            self.assertEqual(
                process_state.installation_id,
                read_src_installation_id(src_root_path),
            )
            self.assertEqual(process_state.webui_port, 22267)

    async def test_process_state_rejects_other_script_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "Temp.process.json"
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()
            write_src_process_state(
                state_path,
                script_id="other-script",
                src_root_path=src_root_path,
                webui_port=22267,
            )

            with self.assertRaisesRegex(ValueError, "other-script"):
                read_src_process_state(
                    state_path,
                    expected_script_id="current-script",
                )

    async def test_process_state_rejects_relative_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "Temp.process.json"
            write_file(
                state_path,
                {
                    "script_id": "script-id",
                    "src_root_path": "relative/SRC",
                    "webui_port": 22267,
                    "config_user_id": None,
                },
            )

            with self.assertRaisesRegex(ValueError, "不是绝对路径"):
                read_src_process_state(state_path)

    async def test_snapshot_state_preserves_config_session_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "Temp.ready"
            root_path = Path(temp_dir) / "SRC"
            root_path.mkdir()
            (root_path / "src.exe").touch()

            write_src_config_snapshot_state(
                state_path,
                script_id="script-id",
                src_root_path=root_path,
                config_user_id="user-id",
            )

            snapshot_state = read_src_config_snapshot_state(
                state_path,
                expected_script_id="script-id",
            )
            self.assertEqual(snapshot_state.src_root_path, root_path.resolve())
            self.assertEqual(
                snapshot_state.installation_id,
                read_src_installation_id(root_path),
            )
            self.assertEqual(snapshot_state.config_user_id, "user-id")

    async def test_script_config_persists_port_before_process_launch(self) -> None:
        task = ScriptConfigTask.__new__(ScriptConfigTask)
        task.src_installation_id = "installation-id"
        task.prepare = AsyncMock()
        task.set_src = AsyncMock()
        task.src_root_path = Path("SRC")
        task.src_set_path = task.src_root_path / "config"
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_process_state_path = Path("data/script-id/Temp.process.json")
        task.temp_ready_path = Path("data/script-id/Temp.ready")
        task.src_process_manager = SimpleNamespace()
        task.wait_event = asyncio.Event()
        task.config_session_started = False
        task.process_cleanup_success = True
        task.prepared = True
        task.script_info = SimpleNamespace(script_id="script-id")
        task.cur_user_item = SimpleNamespace(user_id="user-id")
        events: list[str] = []

        async def fail_process_launch(*_args: object, **_kwargs: object) -> None:
            events.append("launch")
            raise RuntimeError("launch failure")

        task.src_process_manager.open_process = AsyncMock(
            side_effect=fail_process_launch
        )

        with (
            patch(
                "app.task.SRC.ScriptConfig.read_src_webui_port",
                return_value=22267,
            ),
            patch("app.task.SRC.ScriptConfig.validate_src_installation"),
            patch(
                "app.task.SRC.ScriptConfig.write_src_process_state",
                side_effect=lambda *_, **__: events.append("state"),
            ) as write_process_state,
            patch(
                "app.task.SRC.ScriptConfig.write_src_config_snapshot_state",
            ) as write_snapshot_state,
            patch(
                "app.task.SRC.ScriptConfig.kill_src_processes",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.task.SRC.ScriptConfig.save_src_user_config",
            ) as save_user_config,
        ):
            with self.assertRaisesRegex(RuntimeError, "launch failure"):
                await task.main_task()
            await task.final_task()

        write_process_state.assert_called_once_with(
            task.src_process_state_path,
            script_id="script-id",
            src_root_path=task.src_root_path,
            webui_port=22267,
            installation_id=task.src_installation_id,
            config_user_id=None,
        )
        self.assertEqual(events, ["state", "launch"])
        self.assertFalse(task.config_session_started)
        write_snapshot_state.assert_not_called()
        save_user_config.assert_not_called()

    async def test_script_config_marks_session_only_after_process_launch(
        self,
    ) -> None:
        task = ScriptConfigTask.__new__(ScriptConfigTask)
        task.src_installation_id = "installation-id"
        task.prepare = AsyncMock()
        task.set_src = AsyncMock()
        task.src_root_path = Path("SRC")
        task.src_set_path = task.src_root_path / "config"
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_process_state_path = Path("data/script-id/Temp.process.json")
        task.temp_ready_path = Path("data/script-id/Temp.ready")
        task.wait_event = asyncio.Event()
        task.config_session_started = False
        task.script_info = SimpleNamespace(script_id="script-id")
        task.cur_user_item = SimpleNamespace(user_id="user-id")
        events: list[str] = []

        async def open_process(*_args: object, **_kwargs: object) -> None:
            events.append("launch")
            task.wait_event.set()

        task.src_process_manager = SimpleNamespace(
            open_process=AsyncMock(side_effect=open_process)
        )

        with (
            patch(
                "app.task.SRC.ScriptConfig.read_src_webui_port",
                return_value=22267,
            ),
            patch("app.task.SRC.ScriptConfig.validate_src_installation"),
            patch(
                "app.task.SRC.ScriptConfig.write_src_process_state",
                side_effect=lambda *_, **__: events.append("state"),
            ) as write_process_state,
            patch(
                "app.task.SRC.ScriptConfig.write_src_config_snapshot_state",
                side_effect=lambda *_, **__: events.append("snapshot"),
            ) as write_snapshot_state,
        ):
            await task.main_task()

        self.assertEqual(events, ["state", "launch", "snapshot", "state"])
        write_snapshot_state.assert_called_once_with(
            task.temp_ready_path,
            script_id="script-id",
            src_root_path=task.src_root_path,
            installation_id=task.src_installation_id,
            config_user_id="user-id",
        )
        self.assertEqual(
            write_process_state.call_args_list,
            [
                call(
                    task.src_process_state_path,
                    script_id="script-id",
                    src_root_path=task.src_root_path,
                    webui_port=22267,
                    installation_id=task.src_installation_id,
                    config_user_id=None,
                ),
                call(
                    task.src_process_state_path,
                    script_id="script-id",
                    src_root_path=task.src_root_path,
                    webui_port=22267,
                    installation_id=task.src_installation_id,
                    config_user_id="user-id",
                ),
            ],
        )
        self.assertTrue(task.config_session_started)

    async def test_script_config_revalidates_installation_before_launch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_exe_path = root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")

            task = ScriptConfigTask.__new__(ScriptConfigTask)
            task.src_installation_id = read_src_installation_id(root_path)
            task.prepare = AsyncMock()
            task.src_root_path = root_path
            task.src_set_path = root_path / "config"
            task.src_exe_path = src_exe_path
            task.src_process_state_path = root_path / "Temp.process.json"
            task.temp_ready_path = root_path / "Temp.ready"
            task.wait_event = asyncio.Event()
            task.config_session_started = False
            task.script_info = SimpleNamespace(script_id="script-id")
            task.cur_user_item = SimpleNamespace(user_id="user-id")
            task.src_process_manager = SimpleNamespace(open_process=AsyncMock())

            async def replace_installation() -> None:
                src_exe_path.write_bytes(b"installation-B")

            task.set_src = replace_installation

            with (
                patch(
                    "app.task.SRC.ScriptConfig.read_src_webui_port",
                    return_value=22267,
                ),
                patch("app.task.SRC.ScriptConfig.write_src_process_state"),
            ):
                with self.assertRaisesRegex(ValueError, "安装实例"):
                    await task.main_task()

            task.src_process_manager.open_process.assert_not_awaited()

    async def test_script_config_commits_staged_config_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.parent.mkdir()
            src_exe_path.write_bytes(b"installation-A")
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            write_file(
                src_set_path / "src.json",
                {
                    "Alas": {
                        "Emulator": {},
                        "Error": {},
                        "Optimization": {},
                    },
                    "Dungeon": {"PlannerTarget": {}},
                },
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: src\nWebuiPort: 22267\n",
                encoding="utf-8",
            )

            task = ScriptConfigTask.__new__(ScriptConfigTask)
            task.src_installation_id = read_src_installation_id(src_root_path)
            task.src_process_manager = SimpleNamespace()
            task.src_root_path = src_root_path
            task.src_set_path = src_set_path
            task.src_exe_path = src_exe_path
            task.src_webui_port = 22267
            task.script_info = SimpleNamespace(script_id="script-id")
            task.cur_user_item = SimpleNamespace(user_id="user-id")

            with (
                patch(
                    "app.task.SRC.ScriptConfig.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch("app.task.SRC.ScriptConfig.Path.cwd", return_value=work_path),
            ):
                await task.set_src()

            updated_config = read_file(src_set_path / "src.json")
            self.assertEqual(
                updated_config["Alas"]["Emulator"]["GameClient"],
                "android",
            )
            self.assertIn(
                "Run: null",
                (src_set_path / "deploy.yaml").read_text(encoding="utf-8"),
            )
            self.assertFalse(src_set_path.with_name("config.tmp").exists())
            self.assertTrue(src_set_path.with_name("config.old").exists())

    async def test_kills_listener_inside_src_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            process_path = src_root / "toolkit" / "python.exe"
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[connection],
                ),
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                ) as kill_process_by_path,
            ):
                process.return_value.exe.return_value = str(process_path)

                cleanup_success = await kill_src_webui_process(src_root, src_set_path)

            kill_process_by_pid.assert_awaited_once_with(123)
            kill_process_by_path.assert_not_awaited()
            self.assertTrue(cleanup_success)

    async def test_keeps_listener_outside_src_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            src_root = root / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            process_path = root / "Other" / "python.exe"
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[connection],
                ),
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                process.return_value.exe.return_value = str(process_path)

                cleanup_success = await kill_src_webui_process(src_root, src_set_path)

            kill_process_by_pid.assert_not_awaited()
            self.assertTrue(cleanup_success)

    async def test_uses_launch_port_after_config_port_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )
            process_path = src_root / "toolkit" / "python.exe"
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[connection],
                ),
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                process.return_value.exe.return_value = str(process_path)

                cleanup_success = await kill_src_webui_process(
                    src_root,
                    src_set_path,
                    webui_port=22267,
                )

            kill_process_by_pid.assert_awaited_once_with(123)
            self.assertTrue(cleanup_success)

    async def test_missing_webui_port_keeps_legacy_config_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text("Run: src\n", encoding="utf-8")

            with patch(
                "app.task.SRC.tools.process.psutil.net_connections"
            ) as net_connections:
                cleanup_success = await kill_src_webui_process(src_root, src_set_path)

            net_connections.assert_not_called()
            self.assertTrue(cleanup_success)

    async def test_invalid_webui_port_keeps_legacy_config_compatible(self) -> None:
        for webui_port in ("invalid", "70000"):
            with (
                self.subTest(webui_port=webui_port),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                src_root = Path(temp_dir) / "SRC"
                src_set_path = src_root / "config"
                src_set_path.mkdir(parents=True)
                (src_set_path / "deploy.yaml").write_text(
                    f"WebuiPort: {webui_port}\n", encoding="utf-8"
                )

                with patch(
                    "app.task.SRC.tools.process.psutil.net_connections"
                ) as net_connections:
                    cleanup_success = await kill_src_webui_process(
                        src_root, src_set_path
                    )

                net_connections.assert_not_called()
                self.assertTrue(cleanup_success)

    async def test_unreadable_listener_path_reports_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[connection],
                ),
                patch(
                    "app.task.SRC.tools.process.psutil.Process",
                    side_effect=psutil.AccessDenied(pid=123),
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await kill_src_webui_process(src_root, src_set_path)

            kill_process_by_pid.assert_not_awaited()
            self.assertFalse(cleanup_success)

    async def test_failed_taskkill_reports_cleanup_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            process_path = src_root / "toolkit" / "python.exe"
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    return_value=[connection],
                ),
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=False,
                ) as kill_process_by_pid,
            ):
                process.return_value.exe.return_value = str(process_path)

                cleanup_success = await kill_src_webui_process(src_root, src_set_path)

            kill_process_by_pid.assert_awaited_once_with(123)
            self.assertFalse(cleanup_success)

    async def test_process_cleanup_steps_do_not_block_each_other(self) -> None:
        process_manager = SimpleNamespace(
            main_pid=None,
            is_running=AsyncMock(),
            kill=AsyncMock(side_effect=RuntimeError("tracked process failure")),
        )
        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        src_root_path = Path(temp_directory.name) / "SRC"
        src_root_path.mkdir()
        src_exe_path = src_root_path / "src.exe"
        src_set_path = src_root_path / "config"
        src_exe_path.touch()
        src_set_path.mkdir()
        (src_set_path / "src.json").write_text("{}", encoding="utf-8")
        (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

        with (
            patch(
                "app.task.SRC.tools.process.System.kill_process",
                new_callable=AsyncMock,
                return_value=False,
            ) as kill_process,
            patch(
                "app.task.SRC.tools.process._kill_src_root_processes",
                new_callable=AsyncMock,
                return_value=False,
            ) as kill_root_processes,
            patch(
                "app.task.SRC.tools.process.kill_src_webui_process",
                new_callable=AsyncMock,
                return_value=False,
            ) as kill_webui_process,
            patch("app.task.SRC.tools.process.logger"),
        ):
            cleanup_success = await kill_src_processes(
                process_manager,
                src_exe_path=src_exe_path,
                src_root_path=src_root_path,
                src_set_path=src_set_path,
            )

        process_manager.kill.assert_awaited_once_with()
        kill_process.assert_awaited_once_with(src_exe_path)
        self.assertEqual(
            kill_root_processes.await_args_list,
            [call(src_root_path), call(src_root_path)],
        )
        kill_webui_process.assert_awaited_once_with(
            src_root_path,
            src_set_path,
            webui_port=None,
            listener_wait_timeout=0.0,
        )
        process_manager.is_running.assert_not_awaited()
        self.assertFalse(cleanup_success)

    async def test_kills_tracked_process_tree_before_clearing_manager(self) -> None:
        events: list[str] = []
        process_manager = SimpleNamespace(
            main_pid=123,
            is_running=AsyncMock(return_value=True),
            kill=AsyncMock(side_effect=lambda: events.append("manager")),
        )
        temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temp_directory.cleanup)
        src_root_path = Path(temp_directory.name) / "SRC"
        src_root_path.mkdir()
        src_exe_path = src_root_path / "src.exe"
        src_set_path = src_root_path / "config"
        src_exe_path.touch()
        src_set_path.mkdir()
        (src_set_path / "src.json").write_text("{}", encoding="utf-8")
        (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

        with (
            patch(
                "app.task.SRC.tools.process.System.kill_process_by_pid",
                new_callable=AsyncMock,
                side_effect=lambda *_: events.append("tree") or True,
            ) as kill_process_by_pid,
            patch(
                "app.task.SRC.tools.process.System.kill_process",
                new_callable=AsyncMock,
                side_effect=lambda *_: events.append("path") or True,
            ),
            patch(
                "app.task.SRC.tools.process._kill_src_root_processes",
                new_callable=AsyncMock,
                side_effect=lambda *_: events.append("root") or True,
            ),
            patch(
                "app.task.SRC.tools.process.kill_src_webui_process",
                new_callable=AsyncMock,
                side_effect=lambda *_args, **_kwargs: events.append("webui") or True,
            ),
        ):
            cleanup_success = await kill_src_processes(
                process_manager,
                src_exe_path=src_exe_path,
                src_root_path=src_root_path,
                src_set_path=src_set_path,
            )

        kill_process_by_pid.assert_awaited_once_with(123)
        self.assertEqual(
            events,
            ["tree", "path", "root", "manager", "webui", "root"],
        )
        self.assertTrue(cleanup_success)

    async def test_kills_src_helper_before_it_starts_listening(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            helper_path = src_root_path / "toolkit" / "python.exe"
            helper_process = SimpleNamespace(info={"pid": 456, "exe": str(helper_path)})

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.process_iter",
                    return_value=[helper_process],
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await _kill_src_root_processes(src_root_path)

            kill_process_by_pid.assert_awaited_once_with(456)
            self.assertTrue(cleanup_success)

    async def test_unreadable_same_name_helper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            helper_path = src_root_path / "toolkit" / "python.exe"
            helper_path.parent.mkdir(parents=True)
            helper_path.touch()
            helper_process = SimpleNamespace(
                info={"pid": 456, "name": "python.exe", "exe": None}
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.process_iter",
                    return_value=[helper_process],
                ),
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await _kill_src_root_processes(src_root_path)

            kill_process_by_pid.assert_not_awaited()
            self.assertFalse(cleanup_success)

    async def test_rejects_drive_root_cleanup_state(self) -> None:
        process_manager = SimpleNamespace(
            main_pid=None,
            is_running=AsyncMock(),
            kill=AsyncMock(),
        )
        drive_root = Path(Path.cwd().anchor)

        with (
            patch(
                "app.task.SRC.tools.process.System.kill_process",
                new_callable=AsyncMock,
            ) as kill_process,
            patch(
                "app.task.SRC.tools.process.System.kill_process_by_pid",
                new_callable=AsyncMock,
            ) as kill_process_by_pid,
        ):
            cleanup_success = await kill_src_processes(
                process_manager,
                src_exe_path=drive_root / "src.exe",
                src_root_path=drive_root,
                src_set_path=drive_root / "config",
            )

        kill_process.assert_not_awaited()
        kill_process_by_pid.assert_not_awaited()
        process_manager.kill.assert_not_awaited()
        self.assertFalse(cleanup_success)

    async def test_untrusted_cleanup_root_requires_src_config_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with patch(
                "app.task.SRC.tools.process.System.kill_process",
                new_callable=AsyncMock,
            ) as kill_process:
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertFalse(cleanup_success)
            kill_process.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_invalid_config_does_not_block_tracked_process_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()
            process_manager = SimpleNamespace(
                main_pid=123,
                is_running=AsyncMock(return_value=True),
                kill=AsyncMock(),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertFalse(cleanup_success)
            kill_process_by_pid.assert_awaited_once_with(123)
            process_manager.kill.assert_awaited_once_with()
            kill_process.assert_not_awaited()

    async def test_owned_history_can_cleanup_with_valid_config_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_root_path.mkdir()
            (src_root_path / "src.exe").touch()
            backup_set_path = src_root_path / "config.old"
            backup_set_path.mkdir()
            (backup_set_path / "src.json").write_text("{}", encoding="utf-8")
            (backup_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process._kill_src_root_processes",
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
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertTrue(cleanup_success)
            kill_process.assert_awaited_once_with(src_root_path / "src.exe")
            process_manager.kill.assert_awaited_once_with()

    async def test_owned_history_rejects_reused_root_without_config_identity(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "ReusedApp"
            src_root_path.mkdir()
            (src_root_path / "other.exe").touch()
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process._kill_src_root_processes",
                    new_callable=AsyncMock,
                ) as kill_root_processes,
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertFalse(cleanup_success)
            kill_process.assert_not_awaited()
            kill_root_processes.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_owned_history_rejects_in_place_replaced_src_installation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            installation_id = read_src_installation_id(src_root_path)
            src_exe_path.write_bytes(b"installation-B")
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process._kill_src_root_processes",
                    new_callable=AsyncMock,
                ) as kill_root_processes,
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_exe_path,
                    src_root_path=src_root_path,
                    src_set_path=src_set_path,
                    expected_installation_id=installation_id,
                )

            self.assertFalse(cleanup_success)
            kill_process.assert_not_awaited()
            kill_root_processes.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_waits_for_delayed_webui_listener_after_parent_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root = Path(temp_dir) / "SRC"
            src_set_path = src_root / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            process_path = src_root / "toolkit" / "python.exe"
            connection = SimpleNamespace(
                pid=123,
                status=psutil.CONN_LISTEN,
                laddr=SimpleNamespace(port=22267),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.psutil.net_connections",
                    side_effect=[[], [connection]],
                ) as net_connections,
                patch("app.task.SRC.tools.process.psutil.Process") as process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process_by_pid,
                patch(
                    "app.task.SRC.tools.process._WEBUI_LISTENER_RETRY_INTERVAL",
                    0.0,
                ),
            ):
                process.return_value.exe.return_value = str(process_path)
                cleanup_success = await kill_src_webui_process(
                    src_root,
                    src_set_path,
                    listener_wait_timeout=1.0,
                )

            self.assertEqual(net_connections.call_count, 2)
            kill_process_by_pid.assert_awaited_once_with(123)
            self.assertTrue(cleanup_success)

    async def test_auto_proxy_final_cleanup_survives_monitor_failure(self) -> None:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.src_installation_id = "installation-id"
        process_manager = SimpleNamespace()
        task.check_result = "Pass"
        task.prepared = True
        task.src_log_monitor = SimpleNamespace(
            stop=AsyncMock(side_effect=RuntimeError("monitor failure"))
        )
        task.src_process_manager = process_manager
        task.src_root_path = Path("SRC")
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_set_path = task.src_root_path / "config"
        task.src_webui_port = 22267
        task.script_config = SimpleNamespace(get=lambda *_: "KeepEmulator")
        task.cur_user_item = SimpleNamespace(
            log_record={}, name="测试用户", result="未完成", status="运行"
        )
        task.cur_user_uid = "user-id"
        task.cur_user_config = SimpleNamespace()
        task.script_info = SimpleNamespace(name="测试脚本")
        task.task_info = SimpleNamespace(task_id="task-id")
        task.user_start_time = datetime.now()
        task.run_book = False

        with (
            patch(
                "app.task.SRC.AutoProxy.kill_src_processes",
                new_callable=AsyncMock,
                return_value=True,
            ) as kill_processes,
            patch(
                "app.task.SRC.AutoProxy.Config.merge_statistic_info",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.task.SRC.AutoProxy.push_notification",
                new_callable=AsyncMock,
            ),
            patch("app.task.SRC.AutoProxy.logger"),
        ):
            await task.final_task()

        kill_processes.assert_awaited_once_with(
            process_manager,
            src_exe_path=task.src_exe_path,
            src_root_path=task.src_root_path,
            src_set_path=task.src_set_path,
            webui_port=task.src_webui_port,
            listener_wait_timeout=2.0,
            expected_installation_id=task.src_installation_id,
        )
        self.assertEqual(task.cur_user_item.status, "异常")

    async def test_auto_proxy_cleanup_failure_marks_task_abnormal(self) -> None:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.src_installation_id = "installation-id"
        process_manager = SimpleNamespace()
        task.check_result = "Pass"
        task.prepared = True
        task.src_log_monitor = SimpleNamespace(stop=AsyncMock())
        task.src_process_manager = process_manager
        task.src_root_path = Path("SRC")
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_set_path = task.src_root_path / "config"
        task.src_webui_port = 22267
        task.script_config = SimpleNamespace(get=lambda *_: "KeepEmulator")
        task.cur_user_log = SimpleNamespace(status="Success!", content=[])
        log_start_time = datetime.now()
        task.cur_user_item = SimpleNamespace(
            log_record={log_start_time: task.cur_user_log},
            name="测试用户",
            result="未完成",
            status="运行",
        )
        task.cur_user_uid = "user-id"
        task.cur_user_config = SimpleNamespace()
        task.script_info = SimpleNamespace(name="测试脚本")
        task.task_info = SimpleNamespace(task_id="task-id")
        task.user_start_time = datetime.now()
        task.run_book = True
        task._process_cleanup_failure_reported = False

        with (
            patch(
                "app.task.SRC.AutoProxy.kill_src_processes",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.task.SRC.AutoProxy.Config.merge_statistic_info",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                "app.task.SRC.AutoProxy.Config.build_history_log_path",
                return_value=Path("history/test"),
            ),
            patch(
                "app.task.SRC.AutoProxy.Config.save_src_log",
                new_callable=AsyncMock,
            ) as save_src_log,
            patch(
                "app.task.SRC.AutoProxy.Config.send_websocket_message",
                new_callable=AsyncMock,
            ) as send_websocket_message,
            patch(
                "app.task.SRC.AutoProxy.push_notification",
                new_callable=AsyncMock,
            ),
            patch("app.task.SRC.AutoProxy.logger"),
        ):
            await task.final_task()

        self.assertFalse(task.run_book)
        self.assertEqual(task.cur_user_log.status, "SRC 进程清理失败")
        self.assertEqual(task.cur_user_log.content, ["未能完全中止 SRC 进程"])
        self.assertEqual(task.cur_user_item.status, "异常")
        save_src_log.assert_awaited_once_with(
            Path("history/test"),
            ["未能完全中止 SRC 进程"],
            "SRC 进程清理失败",
        )
        send_websocket_message.assert_awaited_once_with(
            id="task-id",
            type="Info",
            data={"Error": "未能完全中止 SRC 进程，请关闭 SRC 后重试"},
        )

    async def test_script_config_cancel_runs_final_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            work_path.mkdir()
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )

            task = ScriptConfigTask.__new__(ScriptConfigTask)
            task.src_installation_id = read_src_installation_id(src_root_path)
            process_manager = SimpleNamespace()
            task.src_process_manager = process_manager
            task.src_root_path = src_root_path
            task.src_exe_path = src_root_path / "src.exe"
            task.src_set_path = src_set_path
            task.src_process_state_path = work_path / "data/script-id/Temp.process.json"
            task.src_webui_port = 22267
            task.config_session_started = True
            task.process_cleanup_success = True
            task.prepared = True
            task.script_info = SimpleNamespace(script_id="script-id")
            task.cur_user_item = SimpleNamespace(user_id="user-id")
            task.accomplish = asyncio.Event()

            main_started = asyncio.Event()

            async def wait_for_cancel() -> None:
                main_started.set()
                await asyncio.Event().wait()

            task.main_task = wait_for_cancel

            with (
                patch(
                    "app.task.SRC.ScriptConfig.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.ScriptConfig.Path.cwd", return_value=work_path),
            ):
                async with asyncio.TaskGroup() as task_group:
                    runner = task_group.create_task(task._execute_task(task_group))
                    await main_started.wait()
                    runner.cancel()

            kill_processes.assert_awaited_once_with(
                process_manager,
                src_exe_path=task.src_exe_path,
                src_root_path=task.src_root_path,
                src_set_path=task.src_set_path,
                webui_port=task.src_webui_port,
                listener_wait_timeout=2.0,
                expected_installation_id=task.src_installation_id,
            )
            copied_config = work_path / "data/script-id/user-id/ConfigFile/src.json"
            self.assertTrue(copied_config.exists())
            process_state = read_src_process_state(task.src_process_state_path)
            self.assertIsNotNone(process_state)
            assert process_state is not None
            self.assertIsNone(process_state.config_user_id)
            self.assertTrue(task.accomplish.is_set())

    async def test_script_config_cleanup_failure_preserves_saved_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            saved_config_path = work_path / "data/script-id/user-id/ConfigFile"
            saved_config_path.mkdir(parents=True)
            saved_config_file = saved_config_path / "src.json"
            saved_config_file.write_text('{"saved": true}', encoding="utf-8")

            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "src.json").write_text(
                '{"replacement": true}', encoding="utf-8"
            )

            task = ScriptConfigTask.__new__(ScriptConfigTask)
            task.src_installation_id = "installation-id"
            task.src_process_manager = SimpleNamespace()
            task.src_root_path = src_root_path
            task.src_exe_path = src_root_path / "src.exe"
            task.src_set_path = src_set_path
            task.src_webui_port = 22267
            task.config_session_started = True
            task.process_cleanup_success = True
            task.prepared = True
            task.script_info = SimpleNamespace(script_id="script-id")
            task.cur_user_item = SimpleNamespace(user_id="user-id")

            with (
                patch(
                    "app.task.SRC.ScriptConfig.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=False,
                ),
                patch("app.task.SRC.ScriptConfig.Path.cwd", return_value=work_path),
            ):
                with self.assertRaisesRegex(RuntimeError, "未能完全中止 SRC 进程"):
                    await task.final_task()

            self.assertEqual(
                saved_config_file.read_text(encoding="utf-8"), '{"saved": true}'
            )

    async def test_script_config_setup_failure_does_not_overwrite_saved_config(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            saved_config_path = work_path / "data/script-id/user-id/ConfigFile"
            saved_config_path.mkdir(parents=True)
            saved_config_file = saved_config_path / "src.json"
            saved_config_file.write_text('{"saved": true}', encoding="utf-8")

            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text('{"live": true}', encoding="utf-8")

            task = ScriptConfigTask.__new__(ScriptConfigTask)
            task.src_installation_id = read_src_installation_id(src_root_path)
            task.src_process_manager = SimpleNamespace()
            task.src_root_path = src_root_path
            task.src_exe_path = src_root_path / "src.exe"
            task.src_set_path = src_set_path
            task.src_webui_port = 22267
            task.config_session_started = False
            task.process_cleanup_success = True
            task.prepared = True
            task.script_info = SimpleNamespace(script_id="script-id")
            task.cur_user_item = SimpleNamespace(user_id="user-id", status="等待")
            task.task_info = SimpleNamespace(task_id="task-id")
            task.accomplish = asyncio.Event()
            task.prepare = AsyncMock()

            with (
                patch(
                    "app.task.SRC.ScriptConfig.kill_src_processes",
                    new_callable=AsyncMock,
                    side_effect=[False, True],
                ) as kill_processes,
                patch(
                    "app.task.SRC.ScriptConfig.Config.send_websocket_message",
                    new_callable=AsyncMock,
                ),
                patch("app.task.SRC.ScriptConfig.Path.cwd", return_value=work_path),
                patch("app.task.SRC.ScriptConfig.logger"),
            ):
                async with asyncio.TaskGroup() as task_group:
                    await task._execute_task(task_group)

            self.assertEqual(kill_processes.await_count, 2)
            self.assertTrue(task.process_cleanup_success)
            self.assertFalse(task.config_session_started)
            self.assertEqual(task.cur_user_item.status, "异常")
            self.assertEqual(
                saved_config_file.read_text(encoding="utf-8"), '{"saved": true}'
            )

    async def test_pre_src_error_stops_retry_when_cleanup_fails(self) -> None:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.src_installation_id = "installation-id"
        task.cur_user_uid = "user-id"
        task.cur_user_item = SimpleNamespace(name="测试用户", status="运行")
        task.cur_user_log = SimpleNamespace(status="", content=[])
        task.task_info = SimpleNamespace(task_id="task-id")
        task.run_book = True
        task._process_cleanup_failure_reported = False
        task.kill_managed_process = AsyncMock(return_value=False)

        with (
            patch(
                "app.task.SRC.AutoProxy.Config.send_websocket_message",
                new_callable=AsyncMock,
            ),
            patch(
                "app.task.SRC.AutoProxy.Notify.push_plyer",
                new_callable=AsyncMock,
            ),
            patch("app.task.SRC.AutoProxy.logger"),
        ):
            cleanup_success = await task.handle_pre_src_error("模拟器启动失败")

        self.assertFalse(cleanup_success)
        self.assertFalse(task.run_book)
        self.assertEqual(task.cur_user_item.status, "异常")
        self.assertEqual(task.cur_user_log.status, "SRC 进程清理失败")

    async def test_src_manager_aggregates_abnormal_user_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            script_uid = uuid.uuid4()
            manager = SrcManager.__new__(SrcManager)
            manager.check_result = "Pass"
            manager.process_cleanup_success = True
            manager.prepared = True
            (Path(temp_dir) / "src.exe").touch()
            manager.src_installation_id = read_src_installation_id(Path(temp_dir))
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                user_list=[SimpleNamespace(status="异常")],
                status="运行",
            )
            manager.temp_path = Path(temp_dir) / "Temp"
            manager.temp_path.mkdir()
            (manager.temp_path / "src.json").write_text("{}", encoding="utf-8")
            (manager.temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            manager.temp_ready_path = manager.temp_path.with_name("Temp.ready")
            manager.src_set_path = Path(temp_dir) / "config"
            manager.src_process_state_path = Path(temp_dir) / "Temp.process.json"
            script_config = SimpleNamespace(unlock=AsyncMock())

            with patch(
                "app.task.SRC.manager.Config.ScriptConfig",
                {script_uid: script_config},
            ):
                await manager.final_task()

        script_config.unlock.assert_awaited_once_with()
        self.assertEqual(manager.script_info.status, "异常")

    async def test_src_manager_preserves_snapshot_when_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            script_uid = uuid.uuid4()
            manager = SrcManager.__new__(SrcManager)
            manager.check_result = "Pass"
            manager.process_cleanup_success = False
            manager.prepared = True
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                user_list=[SimpleNamespace(status="异常")],
                status="运行",
            )
            manager.src_set_path = root_path / "config"
            manager.src_root_path = root_path
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.temp_path.mkdir()
            (manager.temp_path / "src.json").write_text(
                '{"saved": true}', encoding="utf-8"
            )
            script_config = SimpleNamespace(unlock=AsyncMock())

            with patch(
                "app.task.SRC.manager.Config.ScriptConfig",
                {script_uid: script_config},
            ):
                await manager.final_task()

            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertEqual(
                (manager.temp_path / "src.json").read_text(encoding="utf-8"),
                '{"saved": true}',
            )
            self.assertEqual(manager.script_info.status, "异常")

    async def test_src_manager_recovers_preserved_snapshot_before_new_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text('{"live": true}', encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text('{"saved": true}', encoding="utf-8")
            (temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
            )
            process_state_path = work_path / f"data/{script_uid}/Temp.process.json"
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=src_root_path,
                webui_port=22267,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                UserData=SimpleNamespace(toDict=AsyncMock(return_value={})),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig", user_id="user-id")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                current_index=-1,
                user_list=[],
            )
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.EmulatorManager.get_emulator_instance",
                    new_callable=AsyncMock,
                    return_value=SimpleNamespace(),
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager.prepare()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=src_root_path / "src.exe",
                src_root_path=src_root_path,
                src_set_path=src_set_path,
                webui_port=22267,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )
            self.assertTrue(manager.prepared)
            self.assertFalse(process_state_path.exists())
            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"saved": true}',
            )
            self.assertEqual(
                (temp_path / "src.json").read_text(encoding="utf-8"),
                '{"saved": true}',
            )

    async def test_src_manager_recovers_history_before_current_config_check(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            old_root_path = Path(temp_dir) / "OldSRC"
            old_installation_id = "removed-old-installation"
            new_root_path = Path(temp_dir) / "InvalidSRC"
            new_set_path = new_root_path / "config"
            new_set_path.mkdir(parents=True)
            (new_set_path / "src.json").write_text("{}", encoding="utf-8")
            (new_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text('{"original": true}', encoding="utf-8")
            (temp_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=old_root_path,
                installation_id=old_installation_id,
            )
            write_src_process_state(
                work_path / f"data/{script_uid}/Temp.process.json",
                script_id=str(script_uid),
                src_root_path=old_root_path,
                webui_port=22267,
                installation_id=old_installation_id,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                unlock=AsyncMock(),
                get=lambda group, name: (
                    str(new_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(
                mode="ScriptConfig",
                user_id="Default",
                task_id="task-id",
            )
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                status="运行",
            )
            manager._reserved_src_root_path = new_root_path.resolve()
            manager._reserve_src_root = lambda _path: True
            manager.check_result = "-"
            manager.process_cleanup_success = True
            manager.prepared = False
            manager.check = AsyncMock(return_value="src.exe文件不存在")

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch(
                    "app.task.SRC.manager.Config.send_websocket_message",
                    new_callable=AsyncMock,
                ),
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager.main_task()
                await manager.final_task()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=old_root_path / "src.exe",
                src_root_path=old_root_path,
                src_set_path=old_root_path / "config",
                webui_port=22267,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )
            manager.check.assert_awaited_once_with()
            script_config.unlock.assert_awaited_once_with()

    async def test_src_manager_cancel_during_recovery_retries_cleanup_in_final(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text('{"edited": true}', encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text('{"original": true}', encoding="utf-8")
            (temp_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
            )
            write_src_process_state(
                work_path / f"data/{script_uid}/Temp.process.json",
                script_id=str(script_uid),
                src_root_path=src_root_path,
                webui_port=22267,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                unlock=AsyncMock(),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(
                mode="ScriptConfig",
                user_id="Default",
                task_id="task-id",
            )
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                status="运行",
            )
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.check_result = "-"
            manager.process_cleanup_success = True
            manager.prepared = False
            manager.accomplish = asyncio.Event()
            cleanup_started = asyncio.Event()
            cleanup_calls = 0

            async def cleanup(*_args: object, **_kwargs: object) -> bool:
                nonlocal cleanup_calls
                cleanup_calls += 1
                if cleanup_calls == 1:
                    cleanup_started.set()
                    await asyncio.Event().wait()
                return True

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new=cleanup,
                ),
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                async with asyncio.TaskGroup() as task_group:
                    runner = task_group.create_task(manager._execute_task(task_group))
                    await cleanup_started.wait()
                    runner.cancel()

            self.assertEqual(cleanup_calls, 2)
            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertFalse(temp_path.exists())
            script_config.unlock.assert_awaited_once_with()
            self.assertTrue(manager.accomplish.is_set())

    async def test_src_manager_path_change_cleans_old_root_without_restoring_to_new(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            old_root_path = Path(temp_dir) / "OldSRC"
            old_installation_id = "removed-old-installation"
            new_root_path = Path(temp_dir) / "NewSRC"
            new_set_path = new_root_path / "config"
            new_set_path.mkdir(parents=True)
            (new_root_path / "src.exe").touch()
            (new_set_path / "src.json").write_text('{"new": true}', encoding="utf-8")
            (new_set_path / "deploy.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text('{"old": true}', encoding="utf-8")
            (temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=old_root_path,
                installation_id=old_installation_id,
            )
            process_state_path = work_path / f"data/{script_uid}/Temp.process.json"
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=old_root_path,
                webui_port=22267,
                installation_id=old_installation_id,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                UserData=SimpleNamespace(toDict=AsyncMock(return_value={})),
                get=lambda group, name: (
                    str(new_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig", user_id="user-id")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                current_index=-1,
                user_list=[],
            )
            manager._reserved_src_root_path = new_root_path.resolve()
            manager._reserve_src_root = lambda _path: True
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.EmulatorManager.get_emulator_instance",
                    new_callable=AsyncMock,
                    return_value=SimpleNamespace(),
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager.prepare()

            kill_processes.assert_has_awaits(
                [
                    call(
                        ANY,
                        src_exe_path=old_root_path.resolve() / "src.exe",
                        src_root_path=old_root_path.resolve(),
                        src_set_path=old_root_path.resolve() / "config",
                        webui_port=22267,
                        listener_wait_timeout=2.0,
                        expected_installation_id=ANY,
                    ),
                    call(
                        ANY,
                        src_exe_path=new_root_path.resolve() / "src.exe",
                        src_root_path=new_root_path.resolve(),
                        src_set_path=new_root_path.resolve() / "config",
                        webui_port=None,
                        listener_wait_timeout=2.0,
                        expected_installation_id=ANY,
                    ),
                ]
            )
            self.assertEqual(
                (new_set_path / "src.json").read_text(encoding="utf-8"),
                '{"new": true}',
            )
            self.assertEqual(
                (temp_path / "src.json").read_text(encoding="utf-8"),
                '{"new": true}',
            )
            quarantine_paths = list(temp_path.parent.glob("Temp.untrusted-*"))
            self.assertEqual(len(quarantine_paths), 1)
            self.assertEqual(
                (quarantine_paths[0] / "src.json").read_text(encoding="utf-8"),
                '{"old": true}',
            )
            self.assertFalse(process_state_path.exists())

    async def test_src_manager_path_change_restores_existing_old_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            old_root_path = Path(temp_dir) / "OldSRC"
            old_set_path = old_root_path / "config"
            old_set_path.mkdir(parents=True)
            (old_root_path / "src.exe").touch()
            (old_set_path / "src.json").write_text(
                '{"temporary": true}', encoding="utf-8"
            )
            (old_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            new_root_path = Path(temp_dir) / "NewSRC"
            new_set_path = new_root_path / "config"
            new_set_path.mkdir(parents=True)
            (new_set_path / "src.json").write_text(
                '{"new": true}', encoding="utf-8"
            )
            (new_set_path / "deploy.yaml").write_text(
                "WebuiPort: 23333\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            ready_path = temp_path.with_name("Temp.ready")
            write_src_config_snapshot_state(
                ready_path,
                script_id=str(script_uid),
                src_root_path=old_root_path,
            )
            process_state_path = temp_path.with_name("Temp.process.json")
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=old_root_path,
                webui_port=22267,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(new_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager._reserved_src_root_path = new_root_path.resolve()
            manager._reserve_src_root = lambda _path: True
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager._recover_previous_run()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=old_root_path.resolve() / "src.exe",
                src_root_path=old_root_path.resolve(),
                src_set_path=old_root_path.resolve() / "config",
                webui_port=22267,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )
            self.assertFalse(temp_path.exists())
            self.assertFalse(ready_path.exists())
            self.assertFalse(process_state_path.exists())
            self.assertFalse(list(temp_path.parent.glob("Temp.untrusted-*")))
            self.assertEqual(
                (old_set_path / "src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )

    async def test_src_manager_does_not_commit_partial_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_root_path = root_path
            (root_path / "src.exe").touch()
            manager.src_installation_id = read_src_installation_id(root_path)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.src_process_state_path = root_path / "Temp.process.json"
            manager.script_info = SimpleNamespace(script_id="script-id")

            original_copytree = shutil.copytree

            def fail_after_partial_copy(source: Path, destination: Path) -> None:
                destination.mkdir(parents=True)
                (destination / "partial.json").write_text("{}", encoding="utf-8")
                raise OSError("disk failure")

            with patch(
                "app.task.SRC.manager.shutil.copytree",
                side_effect=fail_after_partial_copy,
            ):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    manager._backup_src_config_to_temp()

            self.assertFalse(manager.temp_path.exists())
            self.assertFalse(manager.temp_ready_path.exists())
            self.assertTrue((root_path / "Temp.tmp/partial.json").exists())
            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )

            manager._clear_uncommitted_config_snapshots()
            with patch(
                "app.task.SRC.manager.shutil.copytree",
                side_effect=original_copytree,
            ):
                manager._backup_src_config_to_temp()

            self.assertFalse((root_path / "Temp.tmp").exists())
            self.assertTrue(manager.temp_ready_path.exists())
            self.assertEqual(
                (manager.temp_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )

    async def test_src_manager_rejects_unparseable_snapshot_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_root_path = root_path
            (root_path / "src.exe").touch()
            manager.src_installation_id = read_src_installation_id(root_path)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.script_info = SimpleNamespace(script_id="script-id")

            def copy_unparseable_snapshot(_source: Path, destination: Path) -> Path:
                destination.mkdir(parents=True)
                (destination / "src.json").write_text("{", encoding="utf-8")
                (destination / "deploy.yaml").write_text(
                    "Run: null\n", encoding="utf-8"
                )
                return destination

            with patch(
                "app.task.SRC.manager.shutil.copytree",
                side_effect=copy_unparseable_snapshot,
            ):
                with self.assertRaisesRegex(RuntimeError, "快照副本不完整"):
                    manager._backup_src_config_to_temp()

            self.assertFalse(manager.temp_path.exists())
            self.assertFalse(manager.temp_ready_path.exists())
            self.assertTrue((root_path / "Temp.tmp/src.json").exists())
            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )

    async def test_src_manager_keeps_live_config_when_restore_copy_is_invalid(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_path.mkdir()
            (manager.temp_path / "src.json").write_text(
                '{"snapshot": true}', encoding="utf-8"
            )
            (manager.temp_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            def copy_unparseable_restore(_source: Path, destination: Path) -> Path:
                destination.mkdir(parents=True)
                (destination / "src.json").write_text("{", encoding="utf-8")
                (destination / "deploy.yaml").write_text(
                    "Run: null\n", encoding="utf-8"
                )
                return destination

            with patch(
                "app.task.SRC.manager.shutil.copytree",
                side_effect=copy_unparseable_restore,
            ):
                with self.assertRaisesRegex(RuntimeError, "恢复副本不完整"):
                    manager._restore_src_config_from_temp()

            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertEqual(
                (manager.temp_path / "src.json").read_text(encoding="utf-8"),
                '{"snapshot": true}',
            )

    async def test_src_manager_quarantines_invalid_ready_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text('{"live": true}', encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "partial.json").write_text("{", encoding="utf-8")
            (temp_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                UserData=SimpleNamespace(toDict=AsyncMock(return_value={})),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig", user_id="user-id")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                current_index=-1,
                user_list=[],
            )
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.EmulatorManager.get_emulator_instance",
                    new_callable=AsyncMock,
                    return_value=SimpleNamespace(),
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager.prepare()

            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertEqual(
                (temp_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            quarantine_paths = list(temp_path.parent.glob("Temp.untrusted-*"))
            self.assertEqual(len(quarantine_paths), 1)
            self.assertTrue((quarantine_paths[0] / "partial.json").exists())

    async def test_src_manager_rejects_ownerless_ready_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            ready_path = root_path / "Temp.ready"
            write_file(
                ready_path,
                {"src_root_path": str((root_path / "SRC").resolve())},
                format=".json",
            )
            manager = SrcManager.__new__(SrcManager)
            manager.temp_ready_path = ready_path
            manager.script_info = SimpleNamespace(script_id=str(uuid.uuid4()))

            with self.assertRaisesRegex(ValueError, "所属脚本无效"):
                manager._read_config_snapshot_root()

    async def test_src_manager_rejects_relative_ready_snapshot_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            ready_path = root_path / "Temp.ready"
            script_uid = uuid.uuid4()
            write_file(
                ready_path,
                {
                    "script_id": str(script_uid),
                    "src_root_path": "relative/SRC",
                },
                format=".json",
            )
            manager = SrcManager.__new__(SrcManager)
            manager.temp_ready_path = ready_path
            manager.script_info = SimpleNamespace(script_id=str(script_uid))

            with self.assertRaisesRegex(ValueError, "不是绝对路径"):
                manager._read_config_snapshot_root()

    async def test_src_manager_cleans_owned_process_before_reporting_bad_marker(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text("{}", encoding="utf-8")
            (temp_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            temp_path.with_name("Temp.ready").write_text("{", encoding="utf-8")
            write_src_process_state(
                work_path / f"data/{script_uid}/Temp.process.json",
                script_id=str(script_uid),
                src_root_path=src_root_path,
                webui_port=22267,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
            )
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.prepared = False
            manager.process_cleanup_success = True

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                with self.assertRaisesRegex(RuntimeError, "快照状态无法验证"):
                    await manager._recover_previous_run()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=src_root_path / "src.exe",
                src_root_path=src_root_path,
                src_set_path=src_set_path,
                webui_port=22267,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )

    async def test_src_manager_quarantines_uncommitted_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_path.mkdir()
            (manager.temp_path / "partial.json").write_text("{}", encoding="utf-8")
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.src_process_state_path = root_path / "Temp.process.json"
            write_src_process_state(
                manager.src_process_state_path,
                script_id="script-id",
                src_root_path=manager.src_set_path.parent,
                webui_port=22267,
                installation_id="test-installation",
            )

            manager._quarantine_config_snapshot("测试未提交快照")

            self.assertFalse(manager.temp_path.exists())
            self.assertFalse(manager.src_process_state_path.exists())
            quarantine_paths = list(root_path.glob("Temp.untrusted-*"))
            self.assertEqual(len(quarantine_paths), 1)
            self.assertTrue((quarantine_paths[0] / "partial.json").exists())
            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )

    async def test_src_manager_finishes_interrupted_snapshot_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.temp_path = root_path / "Temp"
            discarded_path = root_path / "Temp.discard"
            discarded_path.mkdir()
            (discarded_path / "src.json").write_text("{}", encoding="utf-8")
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.temp_ready_path.write_text("{}", encoding="utf-8")
            manager.src_process_state_path = root_path / "Temp.process.json"
            manager.src_process_state_path.write_text("{}", encoding="utf-8")

            manager._clear_uncommitted_config_snapshots()

            self.assertFalse(discarded_path.exists())
            self.assertFalse(manager.temp_ready_path.exists())
            self.assertFalse(manager.src_process_state_path.exists())

    async def test_src_manager_restores_snapshot_before_unlock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            script_uid = uuid.uuid4()
            manager = SrcManager.__new__(SrcManager)
            manager.check_result = "Pass"
            manager.process_cleanup_success = True
            manager.prepared = True
            (root_path / "src.exe").touch()
            manager.src_installation_id = read_src_installation_id(root_path)
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                user_list=[SimpleNamespace(status="完成")],
                status="运行",
            )
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.temp_path.mkdir()
            (manager.temp_path / "src.json").write_text(
                '{"saved": true}', encoding="utf-8"
            )
            (manager.temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            manager.src_process_state_path = root_path / "Temp.process.json"

            async def assert_snapshot_restored() -> None:
                self.assertEqual(
                    (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                    '{"saved": true}',
                )
                self.assertFalse(manager.temp_path.exists())

            script_config = SimpleNamespace(
                unlock=AsyncMock(side_effect=assert_snapshot_restored)
            )
            with patch(
                "app.task.SRC.manager.Config.ScriptConfig",
                {script_uid: script_config},
            ):
                await manager.final_task()

            script_config.unlock.assert_awaited_once_with()
            self.assertEqual(manager.script_info.status, "完成")

    async def test_src_manager_does_not_restore_snapshot_damaged_during_task(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            script_uid = uuid.uuid4()
            manager = SrcManager.__new__(SrcManager)
            manager.check_result = "Pass"
            manager.process_cleanup_success = True
            manager.prepared = True
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                user_list=[SimpleNamespace(status="完成")],
                status="运行",
            )
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_path.mkdir()
            (manager.temp_path / "partial.json").write_text("{}", encoding="utf-8")
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.src_process_state_path = root_path / "Temp.process.json"
            script_config = SimpleNamespace(unlock=AsyncMock())

            with patch(
                "app.task.SRC.manager.Config.ScriptConfig",
                {script_uid: script_config},
            ):
                with self.assertRaisesRegex(RuntimeError, "快照不存在或已损坏"):
                    await manager.final_task()

            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertTrue((manager.temp_path / "partial.json").exists())
            script_config.unlock.assert_awaited_once_with()

    async def test_src_manager_cleanup_failure_does_not_notify_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            script_uid = uuid.uuid4()
            manager = SrcManager.__new__(SrcManager)
            manager.check_result = "Pass"
            manager.process_cleanup_success = False
            manager.prepared = True
            manager.begin_time = "2026-08-19 12:00:00"
            manager.task_info = SimpleNamespace(mode="AutoProxy")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                name="测试脚本",
                result="任务结果",
                user_list=[SimpleNamespace(name="测试用户", status="异常")],
                status="运行",
            )
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            manager.temp_path = root_path / "Temp"
            manager.temp_ready_path = root_path / "Temp.ready"
            manager.temp_path.mkdir()
            manager.emulator_manager = SimpleNamespace(close=AsyncMock())
            manager.user_config = SimpleNamespace(toDict=AsyncMock(return_value={}))
            lock_events: list[str] = []

            script_config = SimpleNamespace(
                unlock=AsyncMock(side_effect=lambda: lock_events.append("root-unlock")),
                get=lambda *_: "emulator-index",
                UserData=SimpleNamespace(
                    unlock=AsyncMock(
                        side_effect=lambda: lock_events.append("user-data-unlock")
                    ),
                    load=AsyncMock(
                        side_effect=lambda *_: lock_events.append("user-data-load")
                    ),
                ),
            )
            manager.script_config = script_config

            class ScriptConfigRegistry(dict):
                pass

            script_config_registry = ScriptConfigRegistry({script_uid: script_config})
            script_config_registry.save = AsyncMock()

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    script_config_registry,
                ),
                patch(
                    "app.task.SRC.manager.append_task_game_sign_summary",
                    return_value="任务结果",
                ),
                patch(
                    "app.task.SRC.manager.Notify.push_plyer",
                    new_callable=AsyncMock,
                    side_effect=lambda *_: lock_events.append("notification"),
                ) as push_plyer,
                patch(
                    "app.task.SRC.manager.push_notification",
                    new_callable=AsyncMock,
                ),
            ):
                await manager.final_task()

            self.assertEqual(manager.script_info.status, "异常")
            self.assertIn("存在异常", push_plyer.await_args.args[0])
            self.assertNotIn("已完成", push_plyer.await_args.args[0])
            self.assertEqual(
                lock_events,
                [
                    "user-data-unlock",
                    "user-data-load",
                    "root-unlock",
                    "notification",
                ],
            )

    async def test_missing_historical_src_root_is_safe_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "MovedSRC"
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process.System.kill_process_by_pid",
                    new_callable=AsyncMock,
                ) as kill_process_by_pid,
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertTrue(cleanup_success)
            kill_process.assert_not_awaited()
            kill_process_by_pid.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_trusted_historical_root_without_src_exe_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "MovedSRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "src.json").write_text("{}", encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            process_manager = SimpleNamespace(
                main_pid=None,
                kill=AsyncMock(),
            )

            with (
                patch(
                    "app.task.SRC.tools.process.System.kill_process",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_process,
                patch(
                    "app.task.SRC.tools.process._kill_src_root_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_root_processes,
            ):
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_set_path,
                )

            self.assertFalse(cleanup_success)
            kill_process.assert_not_awaited()
            kill_root_processes.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_rejects_cleanup_root_with_nested_src_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            src_root_path = Path(temp_dir) / "SRC-Suite"
            (src_root_path / "config").mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_root_path / "config/src.json").write_text("{}", encoding="utf-8")
            (src_root_path / "config/deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            nested_root_path = src_root_path / "OtherSRC"
            (nested_root_path / "config").mkdir(parents=True)
            (nested_root_path / "src.exe").touch()
            process_manager = SimpleNamespace(main_pid=None, kill=AsyncMock())

            with patch(
                "app.task.SRC.tools.process.System.kill_process",
                new_callable=AsyncMock,
            ) as kill_process:
                cleanup_success = await kill_src_processes(
                    process_manager,
                    src_exe_path=src_root_path / "src.exe",
                    src_root_path=src_root_path,
                    src_set_path=src_root_path / "config",
                )

            self.assertFalse(cleanup_success)
            kill_process.assert_not_awaited()
            process_manager.kill.assert_not_awaited()

    async def test_src_manager_rejects_path_changed_after_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_root_path = Path(temp_dir) / "OldSRC"
            new_root_path = Path(temp_dir) / "NewSRC"
            script_uid = uuid.uuid4()
            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(new_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
                UserData=SimpleNamespace(toDict=AsyncMock(return_value={})),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig", user_id="Default")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
            )
            manager._reserved_src_root_path = old_root_path.resolve()

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                ) as kill_src,
                patch(
                    "app.task.SRC.manager.EmulatorManager.get_emulator_instance",
                    new_callable=AsyncMock,
                ) as get_emulator,
            ):
                with self.assertRaisesRegex(RuntimeError, "路径在任务启动期间发生变化"):
                    await manager.prepare()

            kill_src.assert_not_awaited()
            get_emulator.assert_not_awaited()

    async def test_src_manager_rejects_foreign_pending_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            script_uid = uuid.uuid4()
            foreign_uid = uuid.uuid4()
            foreign_temp_path = work_path / f"data/{foreign_uid}/Temp"
            foreign_temp_path.mkdir(parents=True)
            write_file(
                foreign_temp_path.with_name("Temp.ready"),
                {
                    "script_id": str(foreign_uid),
                    "src_root_path": str(src_root_path.resolve()),
                },
                format=".json",
            )

            manager = SrcManager.__new__(SrcManager)
            manager.src_root_path = src_root_path
            manager.temp_ready_path = work_path / f"data/{script_uid}/Temp.ready"

            with patch("app.task.SRC.manager.Path.cwd", return_value=work_path):
                with self.assertRaisesRegex(RuntimeError, str(foreign_uid)):
                    manager._assert_no_foreign_pending_snapshot()

    async def test_src_manager_rejects_history_reserved_by_another_task(self) -> None:
        manager = SrcManager.__new__(SrcManager)
        manager.src_root_path = Path("NewSRC").resolve()
        manager._reserve_src_root = lambda _path: False

        with self.assertRaisesRegex(RuntimeError, "已被其他任务占用"):
            manager._reserve_recovery_roots([Path("OldSRC")])

    async def test_src_manager_rejects_unverifiable_foreign_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            script_uid = uuid.uuid4()
            foreign_uid = uuid.uuid4()
            foreign_temp_path = work_path / f"data/{foreign_uid}/Temp"
            foreign_temp_path.mkdir(parents=True)
            foreign_temp_path.with_name("Temp.ready").write_text(
                "{",
                encoding="utf-8",
            )

            manager = SrcManager.__new__(SrcManager)
            manager.src_root_path = Path(temp_dir) / "SRC"
            manager.temp_ready_path = work_path / f"data/{script_uid}/Temp.ready"

            with patch("app.task.SRC.manager.Path.cwd", return_value=work_path):
                with self.assertRaisesRegex(RuntimeError, str(foreign_uid)):
                    manager._assert_no_foreign_pending_snapshot()

    async def test_src_manager_rejects_relative_foreign_snapshot_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            script_uid = uuid.uuid4()
            foreign_uid = uuid.uuid4()
            foreign_temp_path = work_path / f"data/{foreign_uid}/Temp"
            foreign_temp_path.mkdir(parents=True)
            write_file(
                foreign_temp_path.with_name("Temp.ready"),
                {
                    "script_id": str(foreign_uid),
                    "src_root_path": "relative/SRC",
                },
                format=".json",
            )

            manager = SrcManager.__new__(SrcManager)
            manager.src_root_path = Path(temp_dir) / "SRC"
            manager.temp_ready_path = work_path / f"data/{script_uid}/Temp.ready"

            with patch("app.task.SRC.manager.Path.cwd", return_value=work_path):
                with self.assertRaisesRegex(RuntimeError, str(foreign_uid)):
                    manager._assert_no_foreign_pending_snapshot()

    async def test_src_manager_saves_interrupted_config_session_before_restore(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_set_path / "src.json").write_text('{"edited": true}', encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            (src_root_path / "src.exe").touch()

            script_uid = uuid.uuid4()
            user_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text('{"original": true}', encoding="utf-8")
            (temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
                config_user_id=str(user_uid),
            )
            process_state_path = work_path / f"data/{script_uid}/Temp.process.json"
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=src_root_path,
                webui_port=22267,
                config_user_id=str(user_uid),
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                UserData=SimpleNamespace(toDict=AsyncMock(return_value={})),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig", user_id="Default")
            manager.script_info = SimpleNamespace(
                script_id=str(script_uid),
                current_index=-1,
                user_list=[],
            )
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.EmulatorManager.get_emulator_instance",
                    new_callable=AsyncMock,
                    return_value=SimpleNamespace(),
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager.prepare()

            saved_config_path = work_path / f"data/{script_uid}/{user_uid}/ConfigFile"
            self.assertEqual(
                (saved_config_path / "src.json").read_text(encoding="utf-8"),
                '{"edited": true}',
            )
            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertFalse(process_state_path.exists())

    async def test_src_manager_rejects_mismatched_config_session_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            src_set_path = src_root_path / "config"
            src_set_path.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            (src_set_path / "src.json").write_text(
                '{"edited": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            original_user_uid = uuid.uuid4()
            substituted_user_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            temp_path.mkdir(parents=True)
            (temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (temp_path / "deploy.yaml").write_text(
                "WebuiPort: 22267\n", encoding="utf-8"
            )
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
                config_user_id=str(original_user_uid),
            )
            process_state_path = temp_path.with_name("Temp.process.json")
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=src_root_path,
                webui_port=22267,
                config_user_id=str(substituted_user_uid),
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ScriptConfig")
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ),
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                with self.assertRaisesRegex(RuntimeError, "会话归属"):
                    await manager._recover_previous_run()

            substituted_config_path = (
                work_path
                / f"data/{script_uid}/{substituted_user_uid}/ConfigFile"
            )
            self.assertFalse(substituted_config_path.exists())
            self.assertTrue(temp_path.exists())
            self.assertTrue(process_state_path.exists())

    async def test_src_config_restore_rolls_back_failed_directory_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            manager.temp_path.mkdir()
            (manager.temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (manager.temp_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            original_rename = Path.rename

            def fail_staging_promotion(path: Path, target: Path) -> Path:
                if path.name == "config.tmp" and Path(target) == manager.src_set_path:
                    raise OSError("rename failed")
                return original_rename(path, target)

            with patch(
                "app.task.SRC.manager.Path.rename",
                autospec=True,
                side_effect=fail_staging_promotion,
            ):
                with self.assertRaisesRegex(OSError, "rename failed"):
                    manager._restore_src_config_from_temp()

            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertTrue(manager.temp_path.exists())
            self.assertFalse(root_path.joinpath("config.old").exists())

    async def test_src_config_restore_recovers_valid_old_from_invalid_live(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = root_path / "config"
            manager.src_set_path.mkdir()
            (manager.src_set_path / "src.json").write_text("{", encoding="utf-8")
            (manager.src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            backup_path = root_path / "config.old"
            backup_path.mkdir()
            (backup_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (backup_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            manager.temp_path = root_path / "Temp"
            shutil.copytree(backup_path, manager.temp_path)

            manager._restore_src_config_from_temp()

            self.assertEqual(
                (manager.src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertFalse(backup_path.exists())
            quarantine_paths = list(root_path.glob("config.untrusted-*"))
            self.assertEqual(len(quarantine_paths), 1)
            self.assertEqual(
                (quarantine_paths[0] / "src.json").read_text(encoding="utf-8"),
                "{",
            )

    async def test_src_config_restore_rejects_replaced_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_exe_path = root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")
            installation_id = read_src_installation_id(root_path)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"replacement": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            temp_path = root_path / "Temp"
            temp_path.mkdir()
            (temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (temp_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            src_exe_path.write_bytes(b"installation-B")

            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = src_set_path
            manager.temp_path = temp_path

            with self.assertRaisesRegex(ValueError, "安装实例"):
                manager._restore_src_config_from_temp(
                    expected_installation_id=installation_id,
                )

            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"replacement": true}',
            )
            self.assertTrue(temp_path.exists())

    async def test_src_config_restore_rejects_installation_changed_during_copy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_exe_path = root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")
            installation_id = read_src_installation_id(root_path)
            src_set_path = root_path / "config"
            temp_path = root_path / "Temp"
            temp_path.mkdir()
            (temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (temp_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = src_set_path
            manager.temp_path = temp_path
            original_copytree = shutil.copytree

            def replace_installation_after_copy(*args: object, **kwargs: object):
                result = original_copytree(*args, **kwargs)
                src_exe_path.write_bytes(b"installation-B")
                return result

            with patch(
                "app.task.SRC.manager.shutil.copytree",
                side_effect=replace_installation_after_copy,
            ):
                with self.assertRaisesRegex(ValueError, "安装实例"):
                    manager._restore_src_config_from_temp(
                        expected_installation_id=installation_id,
                    )

            self.assertFalse(src_set_path.exists())
            self.assertTrue(temp_path.exists())

    async def test_src_config_restore_rolls_back_installation_changed_at_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"live": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            temp_path = root_path / "Temp"
            temp_path.mkdir()
            (temp_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (temp_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            manager = SrcManager.__new__(SrcManager)
            manager.src_set_path = src_set_path
            manager.temp_path = temp_path

            with patch(
                "app.task.SRC.manager.validate_src_installation",
                side_effect=[None, None, None, ValueError("安装实例已替换")],
            ):
                with self.assertRaisesRegex(ValueError, "安装实例"):
                    manager._restore_src_config_from_temp(
                        expected_installation_id="installation-id",
                    )

            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"live": true}',
            )
            self.assertTrue(temp_path.exists())

    async def test_src_manager_recovers_interrupted_swap_before_process_scan(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            src_root_path = Path(temp_dir) / "SRC"
            (src_root_path / "src.exe").parent.mkdir(parents=True)
            (src_root_path / "src.exe").touch()
            backup_path = src_root_path / "config.old"
            backup_path.mkdir()
            (backup_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (backup_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            staging_path = src_root_path / "config.tmp"
            shutil.copytree(backup_path, staging_path)

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            shutil.copytree(backup_path, temp_path)
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=src_root_path,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(src_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ManualReview")
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager._reserved_src_root_path = src_root_path.resolve()
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager._recover_previous_run()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=src_root_path / "src.exe",
                src_root_path=src_root_path,
                src_set_path=src_root_path / "config",
                webui_port=None,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )
            self.assertEqual(
                (src_root_path / "config/src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertFalse(backup_path.exists())
            self.assertFalse(staging_path.exists())
            self.assertFalse(temp_path.exists())

    async def test_src_manager_recovers_interrupted_swap_in_historical_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            old_root_path = Path(temp_dir) / "OldSRC"
            old_root_path.mkdir()
            (old_root_path / "src.exe").touch()
            backup_path = old_root_path / "config.old"
            backup_path.mkdir()
            (backup_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (backup_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            staging_path = old_root_path / "config.tmp"
            shutil.copytree(backup_path, staging_path)

            new_root_path = Path(temp_dir) / "NewSRC"
            new_set_path = new_root_path / "config"
            new_set_path.mkdir(parents=True)
            (new_set_path / "src.json").write_text(
                '{"new": true}', encoding="utf-8"
            )
            (new_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            script_uid = uuid.uuid4()
            temp_path = work_path / f"data/{script_uid}/Temp"
            shutil.copytree(backup_path, temp_path)
            write_src_config_snapshot_state(
                temp_path.with_name("Temp.ready"),
                script_id=str(script_uid),
                src_root_path=old_root_path,
            )

            script_config = SimpleNamespace(
                lock=AsyncMock(),
                get=lambda group, name: (
                    str(new_root_path)
                    if (group, name) == ("Info", "Path")
                    else "emulator"
                ),
            )
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="ManualReview")
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager._reserved_src_root_path = new_root_path.resolve()
            manager._reserve_src_root = lambda _path: True
            manager.process_cleanup_success = True
            manager.prepared = False

            with (
                patch(
                    "app.task.SRC.manager.Config.ScriptConfig",
                    {script_uid: script_config},
                ),
                patch(
                    "app.task.SRC.manager.kill_src_processes",
                    new_callable=AsyncMock,
                    return_value=True,
                ) as kill_processes,
                patch("app.task.SRC.manager.Path.cwd", return_value=work_path),
            ):
                await manager._recover_previous_run()

            kill_processes.assert_awaited_once_with(
                ANY,
                src_exe_path=old_root_path / "src.exe",
                src_root_path=old_root_path,
                src_set_path=old_root_path / "config",
                webui_port=None,
                listener_wait_timeout=2.0,
                expected_installation_id=ANY,
            )
            self.assertEqual(
                (old_root_path / "config/src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertEqual(
                (new_set_path / "src.json").read_text(encoding="utf-8"),
                '{"new": true}',
            )
            self.assertFalse(backup_path.exists())
            self.assertFalse(staging_path.exists())
            self.assertFalse(temp_path.exists())

    async def test_src_manager_keeps_pending_session_when_source_was_moved(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            script_uid = uuid.uuid4()
            user_uid = uuid.uuid4()
            process_state_path = root_path / "Temp.process.json"
            process_state = SrcProcessState(
                script_id=str(script_uid),
                src_root_path=root_path / "missing-src",
                installation_id="removed-installation",
                webui_port=22267,
                config_user_id=str(user_uid),
            )
            write_src_process_state(
                process_state_path,
                script_id=str(script_uid),
                src_root_path=process_state.src_root_path,
                webui_port=process_state.webui_port,
                installation_id=process_state.installation_id,
                config_user_id=process_state.config_user_id,
            )

            manager = SrcManager.__new__(SrcManager)
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager.src_process_state_path = process_state_path

            with self.assertRaisesRegex(RuntimeError, "已保留待恢复状态"):
                manager._save_pending_config_session(process_state)

            self.assertTrue(process_state_path.exists())
            self.assertFalse(
                (root_path / f"data/{script_uid}/{user_uid}/ConfigFile").exists()
            )

    async def test_src_manager_promotes_committed_user_config_without_source(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir) / "work"
            script_uid = uuid.uuid4()
            user_uid = uuid.uuid4()
            missing_src_root = Path(temp_dir) / "missing-src"
            process_state_path = (
                work_path / f"data/{script_uid}/Temp.process.json"
            )
            process_state = SrcProcessState(
                script_id=str(script_uid),
                src_root_path=missing_src_root,
                installation_id="removed-installation",
                webui_port=22267,
                config_user_id=str(user_uid),
            )
            write_src_process_state(
                process_state_path,
                script_id=process_state.script_id,
                src_root_path=process_state.src_root_path,
                webui_port=process_state.webui_port,
                installation_id=process_state.installation_id,
                config_user_id=process_state.config_user_id,
            )
            config_path = (
                work_path
                / "data"
                / str(script_uid)
                / str(user_uid)
                / "ConfigFile"
            )
            staging_path = config_path.with_name("ConfigFile.tmp")
            staging_path.mkdir(parents=True)
            (staging_path / "src.json").write_text(
                '{"edited": true}', encoding="utf-8"
            )
            (staging_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            write_file(
                config_path.with_name("ConfigFile.tmp.ready"),
                {"ready": True},
                format=".json",
            )

            manager = SrcManager.__new__(SrcManager)
            manager.script_info = SimpleNamespace(script_id=str(script_uid))
            manager.src_process_state_path = process_state_path

            with patch("app.task.SRC.manager.Path.cwd", return_value=work_path):
                manager._save_pending_config_session(process_state)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"edited": true}',
            )
            self.assertFalse(staging_path.exists())
            self.assertFalse(config_path.with_name("ConfigFile.tmp.ready").exists())
            recovered_state = read_src_process_state(
                process_state_path,
                expected_script_id=str(script_uid),
            )
            self.assertIsNotNone(recovered_state)
            assert recovered_state is not None
            self.assertIsNone(recovered_state.config_user_id)

    async def test_user_config_save_rolls_back_failed_directory_swap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text('{"new": true}', encoding="utf-8")
            (src_set_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            config_path = root_path / "ConfigFile"
            config_path.mkdir()
            (config_path / "src.json").write_text('{"old": true}', encoding="utf-8")
            (config_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            original_rename = Path.rename

            def fail_staging_promotion(path: Path, target: Path) -> Path:
                if path.name == "ConfigFile.tmp" and Path(target) == config_path:
                    raise OSError("rename failed")
                return original_rename(path, target)

            with patch(
                "app.task.SRC.tools.config.Path.rename",
                autospec=True,
                side_effect=fail_staging_promotion,
            ):
                with self.assertRaisesRegex(OSError, "rename failed"):
                    save_src_user_config(src_set_path, config_path)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"old": true}',
            )
            self.assertTrue((root_path / "ConfigFile.tmp.ready").exists())

            save_src_user_config(src_set_path, config_path)
            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"new": true}',
            )
            self.assertFalse((root_path / "ConfigFile.old").exists())
            self.assertFalse((root_path / "ConfigFile.tmp").exists())

    async def test_user_config_save_rejects_installation_changed_during_copy(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_root_path = root_path / "SRC"
            src_exe_path = src_root_path / "src.exe"
            src_exe_path.parent.mkdir()
            src_exe_path.write_bytes(b"installation-A")
            installation_id = read_src_installation_id(src_root_path)
            src_set_path = src_root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"new": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            config_path = root_path / "ConfigFile"
            config_path.mkdir()
            (config_path / "src.json").write_text(
                '{"old": true}', encoding="utf-8"
            )
            (config_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            original_copytree = shutil.copytree

            def replace_installation_after_copy(*args: object, **kwargs: object):
                result = original_copytree(*args, **kwargs)
                src_exe_path.write_bytes(b"installation-B")
                return result

            with patch(
                "app.task.SRC.tools.config.shutil.copytree",
                side_effect=replace_installation_after_copy,
            ):
                with self.assertRaisesRegex(ValueError, "安装实例"):
                    save_src_user_config(
                        src_set_path,
                        config_path,
                        expected_installation_id=installation_id,
                    )

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"old": true}',
            )
            self.assertFalse((root_path / "ConfigFile.tmp.ready").exists())

    async def test_src_config_update_rejects_replaced_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_exe_path = root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")
            installation_id = read_src_installation_id(root_path)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            staging_path = stage_src_config_update(
                src_set_path,
                expected_installation_id=installation_id,
            )
            (staging_path / "src.json").write_text(
                '{"staged": true}', encoding="utf-8"
            )
            src_exe_path.write_bytes(b"installation-B")
            (src_set_path / "src.json").write_text(
                '{"replacement": true}', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "安装实例"):
                promote_src_config_update(
                    src_set_path,
                    staging_path,
                    expected_installation_id=installation_id,
                )

            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"replacement": true}',
            )
            self.assertTrue(staging_path.exists())

    async def test_src_config_update_rolls_back_installation_changed_at_commit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_exe_path = root_path / "src.exe"
            src_exe_path.write_bytes(b"installation-A")
            installation_id = read_src_installation_id(root_path)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"original": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            staging_path = stage_src_config_update(
                src_set_path,
                expected_installation_id=installation_id,
            )
            (staging_path / "src.json").write_text(
                '{"staged": true}', encoding="utf-8"
            )

            with patch(
                "app.task.SRC.tools.config.validate_src_installation",
                side_effect=[None, ValueError("安装实例已替换")],
            ):
                with self.assertRaisesRegex(ValueError, "安装实例"):
                    promote_src_config_update(
                        src_set_path,
                        staging_path,
                        expected_installation_id=installation_id,
                    )

            self.assertEqual(
                (src_set_path / "src.json").read_text(encoding="utf-8"),
                '{"original": true}',
            )
            self.assertTrue(staging_path.exists())

    async def test_user_config_commit_marker_survives_until_state_clear(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            src_set_path = root_path / "config"
            src_set_path.mkdir()
            (src_set_path / "src.json").write_text(
                '{"new": true}', encoding="utf-8"
            )
            (src_set_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )
            config_path = root_path / "ConfigFile"
            config_path.mkdir()
            (config_path / "src.json").write_text(
                '{"old": true}', encoding="utf-8"
            )
            (config_path / "deploy.yaml").write_text(
                "Run: null\n", encoding="utf-8"
            )

            save_src_user_config(
                src_set_path,
                config_path,
                preserve_commit_marker=True,
            )

            ready_path = root_path / "ConfigFile.tmp.ready"
            self.assertTrue(ready_path.exists())
            self.assertTrue((root_path / "ConfigFile.old").exists())
            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"new": true}',
            )

            recover_src_user_config(config_path)

            self.assertFalse(ready_path.exists())
            self.assertFalse((root_path / "ConfigFile.old").exists())

    async def test_user_config_recovers_committed_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            config_path = root_path / "ConfigFile"
            staging_path = root_path / "ConfigFile.tmp"
            staging_path.mkdir()
            (staging_path / "src.json").write_text(
                '{"recovered": true}', encoding="utf-8"
            )
            (staging_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_file(
                root_path / "ConfigFile.tmp.ready",
                {"ready": True},
                format=".json",
            )

            recover_src_user_config(config_path)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"recovered": true}',
            )
            self.assertFalse(staging_path.exists())
            self.assertFalse((root_path / "ConfigFile.tmp.ready").exists())

    async def test_checks_recover_user_config_before_existence_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_path = Path(temp_dir)
            script_id = "script-id"

            def prepare_committed_staging(config_path: Path, value: str) -> None:
                staging_path = config_path.with_name("ConfigFile.tmp")
                staging_path.mkdir(parents=True)
                (staging_path / "src.json").write_text(value, encoding="utf-8")
                (staging_path / "deploy.yaml").write_text(
                    "Run: null\n", encoding="utf-8"
                )
                write_file(
                    config_path.with_name("ConfigFile.tmp.ready"),
                    {"ready": True},
                    format=".json",
                )

            default_config_path = (
                work_path / f"data/{script_id}/Default/ConfigFile"
            )
            prepare_committed_staging(default_config_path, '{"default": true}')
            manager = SrcManager.__new__(SrcManager)
            manager.task_info = SimpleNamespace(mode="AutoProxy")
            manager.script_info = SimpleNamespace(script_id=script_id)

            with patch("app.task.SRC.manager.Path.cwd", return_value=work_path):
                manager._recover_default_user_config_transaction()

            self.assertEqual(
                (default_config_path / "src.json").read_text(encoding="utf-8"),
                '{"default": true}',
            )

            user_id = uuid.uuid4()
            detail_config_path = work_path / f"data/{script_id}/{user_id}/ConfigFile"
            prepare_committed_staging(detail_config_path, '{"detail": true}')
            task = AutoProxyTask.__new__(AutoProxyTask)
            task.script_config = SimpleNamespace(get=lambda *_: 0)
            task.cur_user_config = SimpleNamespace(
                get=lambda group, name: (
                    "详细" if (group, name) == ("Info", "Mode") else 0
                )
            )
            task.cur_user_item = SimpleNamespace(status="等待")
            task.cur_user_uid = user_id
            task.script_info = SimpleNamespace(script_id=script_id)

            with patch("app.task.SRC.AutoProxy.Path.cwd", return_value=work_path):
                self.assertEqual(await task.check(), "Pass")

            self.assertEqual(
                (detail_config_path / "src.json").read_text(encoding="utf-8"),
                '{"detail": true}',
            )

    async def test_user_config_prefers_valid_committed_staging_over_invalid_current(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            config_path = root_path / "ConfigFile"
            config_path.mkdir()
            (config_path / "partial.json").write_text("{}", encoding="utf-8")
            staging_path = root_path / "ConfigFile.tmp"
            staging_path.mkdir()
            (staging_path / "src.json").write_text('{"edited": true}', encoding="utf-8")
            (staging_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_file(
                root_path / "ConfigFile.tmp.ready",
                {"ready": True},
                format=".json",
            )

            recover_src_user_config(config_path)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"edited": true}',
            )
            self.assertEqual(
                len(list(root_path.glob("ConfigFile.untrusted-*"))),
                1,
            )

    async def test_user_config_prefers_committed_staging_over_invalid_backup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            config_path = root_path / "ConfigFile"
            backup_path = root_path / "ConfigFile.old"
            backup_path.mkdir()
            (backup_path / "partial.json").write_text("{}", encoding="utf-8")
            staging_path = root_path / "ConfigFile.tmp"
            staging_path.mkdir()
            (staging_path / "src.json").write_text('{"edited": true}', encoding="utf-8")
            (staging_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")
            write_file(
                root_path / "ConfigFile.tmp.ready",
                {"ready": True},
                format=".json",
            )

            recover_src_user_config(config_path)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"edited": true}',
            )
            self.assertFalse(backup_path.exists())

    async def test_user_config_restores_backup_when_promoted_copy_is_damaged(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_path = Path(temp_dir)
            config_path = root_path / "ConfigFile"
            config_path.mkdir()
            (config_path / "partial.json").write_text("{}", encoding="utf-8")
            backup_path = root_path / "ConfigFile.old"
            backup_path.mkdir()
            (backup_path / "src.json").write_text('{"old": true}', encoding="utf-8")
            (backup_path / "deploy.yaml").write_text("Run: null\n", encoding="utf-8")

            recover_src_user_config(config_path)

            self.assertEqual(
                (config_path / "src.json").read_text(encoding="utf-8"),
                '{"old": true}',
            )
            self.assertFalse(backup_path.exists())
            self.assertEqual(
                len(list(root_path.glob("ConfigFile.untrusted-*"))),
                1,
            )

    async def test_script_config_save_failure_preserves_live_config_barrier(
        self,
    ) -> None:
        task = ScriptConfigTask.__new__(ScriptConfigTask)
        task.src_installation_id = "installation-id"
        task.prepared = True
        task.config_session_started = True
        task.process_cleanup_success = True
        task.src_process_manager = SimpleNamespace()
        task.src_root_path = Path("SRC")
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_set_path = task.src_root_path / "config"
        task.src_webui_port = 22267
        task.script_info = SimpleNamespace(script_id="script-id")
        task.cur_user_item = SimpleNamespace(user_id="Default")

        with (
            patch(
                "app.task.SRC.ScriptConfig.kill_src_processes",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.task.SRC.ScriptConfig.save_src_user_config",
                side_effect=OSError("save failed"),
            ),
            patch("app.task.SRC.ScriptConfig.validate_src_installation"),
        ):
            with self.assertRaisesRegex(OSError, "save failed"):
                await task.final_task()

        self.assertFalse(task.process_cleanup_success)

    async def test_src_manager_emulator_timeout_still_persists_results(self) -> None:
        script_uid = uuid.uuid4()
        manager = SrcManager.__new__(SrcManager)
        manager.process_cleanup_success = True
        manager.task_info = SimpleNamespace(mode="AutoProxy")
        manager.script_info = SimpleNamespace(
            script_id=str(script_uid),
            user_list=[SimpleNamespace(status="完成")],
            status="运行",
        )

        async def never_closes(*_args: object) -> None:
            await asyncio.Event().wait()

        manager.emulator_manager = SimpleNamespace(close=never_closes)
        manager.user_config = SimpleNamespace(
            toDict=AsyncMock(return_value={"saved": True})
        )
        script_config = SimpleNamespace(
            get=lambda *_: "emulator-index",
            UserData=SimpleNamespace(
                unlock=AsyncMock(),
                load=AsyncMock(),
            ),
        )
        manager.script_config = script_config

        class ScriptConfigRegistry(dict):
            pass

        script_config_registry = ScriptConfigRegistry({script_uid: script_config})
        script_config_registry.save = AsyncMock()

        with (
            patch(
                "app.task.SRC.manager.Config.ScriptConfig",
                script_config_registry,
            ),
            patch("app.task.SRC.manager._EMULATOR_CLOSE_TIMEOUT_SECONDS", 0.01),
            patch("app.task.SRC.manager.logger"),
        ):
            should_notify = await asyncio.wait_for(
                manager._complete_locked_final_task(),
                timeout=1,
            )

        self.assertTrue(should_notify)
        self.assertEqual(manager.script_info.status, "异常")
        script_config.UserData.unlock.assert_awaited_once_with()
        script_config.UserData.load.assert_awaited_once_with({"saved": True})
        script_config_registry.save.assert_awaited_once_with()

    async def test_auto_proxy_final_notifications_cannot_block_cleanup(self) -> None:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.src_installation_id = "installation-id"
        task.check_result = "Pass"
        task.prepared = True
        task.src_log_monitor = SimpleNamespace(stop=AsyncMock())
        task.src_process_manager = SimpleNamespace()
        task.src_root_path = Path("SRC")
        task.src_exe_path = task.src_root_path / "src.exe"
        task.src_set_path = task.src_root_path / "config"
        task.src_webui_port = 22267
        task.script_config = SimpleNamespace(
            get=lambda group, name: (
                "ExitEmulator"
                if (group, name) == ("Run", "TaskTransitionMethod")
                else "emulator-index"
            )
        )
        task.emulator_manager = SimpleNamespace(close=AsyncMock())
        task.cur_user_item = SimpleNamespace(
            log_record={},
            name="测试用户",
            result="完成",
            status="运行",
        )
        task.cur_user_uid = "user-id"
        task.cur_user_config = SimpleNamespace(
            get=lambda group, name: (
                0 if (group, name) == ("Data", "ProxyTimes") else -1
            ),
            set=AsyncMock(),
        )
        task.script_info = SimpleNamespace(name="测试脚本")
        task.task_info = SimpleNamespace(task_id="task-id")
        task.user_start_time = datetime.now()
        task.run_book = True
        task._process_cleanup_failure_reported = False

        async def never_finishes(*_args: object, **_kwargs: object) -> None:
            await asyncio.Event().wait()

        task.src_log_monitor.stop = never_finishes
        task.emulator_manager.close = never_finishes

        with (
            patch(
                "app.task.SRC.AutoProxy.kill_src_processes",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.task.SRC.AutoProxy.Config.merge_statistic_info",
                new_callable=AsyncMock,
                return_value={},
            ),
            patch("app.task.SRC.AutoProxy.push_notification", new=never_finishes),
            patch(
                "app.task.SRC.AutoProxy.Config.send_websocket_message",
                new=never_finishes,
            ),
            patch("app.task.SRC.AutoProxy.Notify.push_plyer", new=never_finishes),
            patch(
                "app.task.SRC.AutoProxy._FINAL_NOTIFICATION_TIMEOUT_SECONDS",
                0.01,
            ),
            patch("app.task.SRC.AutoProxy._FINAL_REPORT_TIMEOUT_SECONDS", 0.01),
            patch("app.task.SRC.AutoProxy._FINAL_CLEANUP_TIMEOUT_SECONDS", 0.01),
            patch("app.task.SRC.AutoProxy.logger"),
        ):
            await asyncio.wait_for(task.final_task(), timeout=1)

        self.assertEqual(task.cur_user_item.status, "完成")
        task.cur_user_config.set.assert_awaited_once_with(
            "Data",
            "ProxyTimes",
            1,
        )

    async def test_src_notification_timeout_does_not_block_other_channels(self) -> None:
        manager = SrcManager.__new__(SrcManager)
        manager.task_info = SimpleNamespace(mode="AutoProxy", task_id="task-id")
        manager.script_info = SimpleNamespace(
            name="测试脚本",
            status="完成",
            result="任务结果",
            user_list=[SimpleNamespace(name="测试用户", status="完成")],
        )
        manager.begin_time = "2026-08-19 12:00:00"

        async def never_finishes(*_args: object) -> None:
            await asyncio.Event().wait()

        with (
            patch(
                "app.task.SRC.manager.Notify.push_plyer",
                new=never_finishes,
            ),
            patch(
                "app.task.SRC.manager.push_notification",
                new_callable=AsyncMock,
            ) as push_notification,
            patch(
                "app.task.SRC.manager.Config.send_websocket_message",
                new_callable=AsyncMock,
            ),
            patch("app.task.SRC.manager._NOTIFICATION_TIMEOUT_SECONDS", 0.01),
        ):
            await asyncio.wait_for(manager._send_final_notification(), timeout=1)

        push_notification.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
