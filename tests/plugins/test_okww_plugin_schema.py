from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

PLUGIN_SRC = Path(__file__).parents[2] / "plugins" / "okww_adapter" / "src"
sys.path.insert(0, str(PLUGIN_SRC))

from app.utils.ProcessManager import ProcessManager  # noqa: E402
from okww_adapter.adapter import autoproxy  # noqa: E402
from okww_adapter.adapter.autoproxy import (  # noqa: E402
    AutoProxyTask,
    _OKWW_REL_APP_JSON,
    _OKWW_REL_CONFIG_DIR,
    _configure_okww_launcher,
    _ensure_okww_user_config,
    _okww_mas_config_dir,
)
from okww_adapter.plugin import Plugin  # noqa: E402
from okww_adapter.schema import OkwwUserConfig  # noqa: E402
from okww_adapter.wuthering_waves import (  # noqa: E402
    resolve_wuthering_waves_process_path,
)


class ConfigStub:
    def __init__(self, values: dict[tuple[str, str], object]) -> None:
        self.values = values

    def get(self, section: str, key: str) -> object:
        return self.values[(section, key)]


class ProcessManagerStub(ProcessManager):
    def __init__(self) -> None:
        self.target_process = None
        self.opened: tuple[Path, tuple[str, ...]] | None = None
        self.searched_exe: str | None = None

    async def open_process(self, program: Path, *args: str) -> None:
        self.opened = (program, args)

    async def search_process(self, target, deadline) -> None:
        self.searched_exe = target.exe


class OkwwPluginSchemaTest(unittest.TestCase):
    def test_descriptor_supports_native_config_session(self) -> None:
        definition = Plugin(None).build_script_adapters()[0]  # type: ignore[arg-type]

        self.assertEqual(definition.supported_modes, ("AutoProxy", "ScriptConfig"))
        self.assertIsNone(definition.metadata.get("client"))

    def test_simple_mode_and_daily_task_are_the_defaults(self) -> None:
        config = OkwwUserConfig()

        self.assertEqual(config.Info.Mode, "简洁")
        self.assertEqual(config.Task.TaskIndex, 1)

    def test_legacy_task_index_two_maps_to_multi_account_task(self) -> None:
        config = OkwwUserConfig.model_validate({"Task": {"TaskIndex": 2}})

        self.assertEqual(config.Task.TaskIndex, 7)

    def test_configure_action_starts_script_config_session(self) -> None:
        definition = Plugin(None).build_script_adapters()[0]  # type: ignore[arg-type]
        provider = definition.build_provider(owner="test")
        action_group = next(
            group for group in provider.user_schema["groups"] if group["key"] == "Action"
        )
        field = action_group["fields"][0]
        action = field["action"]

        self.assertEqual(field["type"], "action")
        self.assertEqual(action["path"], "/api/dispatch/start")
        self.assertEqual(
            action["payload"],
            {"taskId": "{{userId}}", "mode": "ScriptConfig"},
        )
        self.assertEqual(action["session"]["stop_path"], "/api/dispatch/stop")


class OkwwPluginRuntimeParityTest(unittest.TestCase):
    def test_official_launcher_resolves_real_client(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            launcher = root / "launcher.exe"
            launcher.touch()
            install_dir = root / "Wuthering Waves Game"
            client = (
                install_dir
                / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
            )
            client.parent.mkdir(parents=True)
            client.touch()
            payload = json.dumps({"installDirPath": str(install_dir)}).encode()
            encoded = base64.b64encode(bytes(value ^ 0x63 for value in payload))
            preference = root / "kr_game_cache/kr_game_temp.bin"
            preference.parent.mkdir()
            preference.write_bytes(encoded)

            self.assertEqual(resolve_wuthering_waves_process_path(launcher), client)

    def test_launcher_config_preserves_unmanaged_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app_json = root / _OKWW_REL_APP_JSON
            app_json.parent.mkdir(parents=True)
            app_json.write_text(
                json.dumps(
                    {
                        "auto_start": False,
                        "current_profile": "China",
                        "update_method": "ASK",
                        "profiles": [{"name": "China"}, {"name": "Global"}],
                        "keep": True,
                    }
                ),
                encoding="utf-8",
            )

            _configure_okww_launcher(root, "国际服")

            config = json.loads(app_json.read_text(encoding="utf-8"))
            self.assertTrue(config["auto_start"])
            self.assertEqual(config["current_profile"], "Global")
            self.assertEqual(config["update_method"], "AUTO_UPDATE")
            self.assertTrue(config["keep"])

    def test_simple_and_detailed_modes_use_different_owners(self) -> None:
        script_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            Path, "cwd", return_value=Path(temp_dir)
        ):
            simple = _okww_mas_config_dir(script_id, user_id, "简洁")
            detailed = _okww_mas_config_dir(script_id, user_id, "详细")

        self.assertEqual(simple.parts[-2:], ("Default", "ConfigFile"))
        self.assertEqual(detailed.parts[-2:], (user_id, "ConfigFile"))

    def test_missing_user_config_is_initialized_from_okww(self) -> None:
        script_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            Path, "cwd", return_value=Path(temp_dir)
        ):
            script_root = Path(temp_dir) / "okww"
            source = script_root / _OKWW_REL_CONFIG_DIR
            source.mkdir(parents=True)
            (source / "DailyTask.json").write_text('{"keep": true}', encoding="utf-8")

            target = _ensure_okww_user_config(
                script_root, script_id, user_id, "简洁"
            )

            self.assertEqual(
                json.loads((target / "DailyTask.json").read_text(encoding="utf-8")),
                {"keep": True},
            )

    def test_old_per_user_copy_recovers_simple_mode_config(self) -> None:
        script_id = str(uuid.uuid4())
        user_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            Path, "cwd", return_value=Path(temp_dir)
        ):
            script_root = Path(temp_dir) / "okww"
            current = script_root / _OKWW_REL_CONFIG_DIR
            current.mkdir(parents=True)
            (current / "DailyTask.json").write_text(
                '{"source": "okww"}', encoding="utf-8"
            )
            old_user_dir = (
                Path(temp_dir) / "data" / script_id / user_id / "ConfigFile"
            )
            old_user_dir.mkdir(parents=True)
            (old_user_dir / "DailyTask.json").write_text(
                '{"source": "legacy"}', encoding="utf-8"
            )

            target = _ensure_okww_user_config(
                script_root, script_id, user_id, "简洁"
            )

            self.assertEqual(
                json.loads((target / "DailyTask.json").read_text(encoding="utf-8")),
                {"source": "legacy"},
            )

    def test_mas_overrides_preserve_unmanaged_daily_task_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            task = AutoProxyTask.__new__(AutoProxyTask)
            task.script_config_path = Path(temp_dir)
            task.cur_user_config = ConfigStub(
                {
                    ("Task", "WhichToFarm"): "Forgery Challenge",
                    ("Task", "WhichTacetSuppressionToFarm"): 2,
                    ("Task", "WhichForgeryChallengeToFarm"): 3,
                    ("Task", "MaterialSelection"): "Shell Credit",
                    ("Task", "FarmNightmareNestForDailyEcho"): True,
                    ("Task", "AdditionalTasks"): ["Check Weekly Garden"],
                }
            )
            daily_task = task.script_config_path / "DailyTask.json"
            daily_task.write_text('{"Unmanaged Option": 42}', encoding="utf-8")

            task._apply_mas_overrides()

            config = json.loads(daily_task.read_text(encoding="utf-8"))
            self.assertEqual(config["Unmanaged Option"], 42)
            self.assertEqual(config["Which to Farm"], "Forgery Challenge")

    def test_window_closed_log_is_required_for_success(self) -> None:
        success = self._make_log_task(is_running=True)
        asyncio.run(
            success.check_log(
                ["MainWindow:Window closed exit_event.is_set\n"], datetime.now()
            )
        )
        early_exit = self._make_log_task(is_running=False)
        asyncio.run(
            early_exit.check_log(["TaskExecutor:Executor destroy\n"], datetime.now())
        )

        self.assertEqual(success.cur_user_log.status, "Success!")
        self.assertEqual(early_exit.cur_user_log.status, "OK-WW 在完成任务前退出")
        self.assertEqual(early_exit.cur_user_item.status, "异常")

    def test_running_game_is_tracked_by_resolved_client_path(self) -> None:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.game_process_path = Path(
            "D:/Wuthering Waves/Client/Binaries/Win64/Client-Win64-Shipping.exe"
        )
        task.game_manager = ProcessManagerStub()
        with patch.object(autoproxy, "is_process_running", return_value=True):
            asyncio.run(task._mas_launch_game_before_task())

        self.assertIsNone(task.game_manager.opened)
        self.assertEqual(task.game_manager.searched_exe, str(task.game_process_path))

    @staticmethod
    def _make_log_task(*, is_running: bool) -> AutoProxyTask:
        task = AutoProxyTask.__new__(AutoProxyTask)
        task.cur_user_log = SimpleNamespace(content=[], status="")
        task.cur_user_item = SimpleNamespace(status="运行")
        task.script_info = SimpleNamespace(log="")
        task.script_config = ConfigStub({("Run", "RunTimeLimit"): 60})
        task.okww_process_manager = SimpleNamespace(
            is_running=AsyncMock(return_value=is_running)
        )
        task.wait_event = asyncio.Event()
        return task


if __name__ == "__main__":
    unittest.main()
