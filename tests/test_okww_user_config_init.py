import base64
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api import scripts as scripts_api
from app.core.config import AppConfig
from app.models.ConfigBase import MultipleConfig
from app.models.config import OkwwConfig, OkwwUserConfig
from app.models.schema import OkwwConfig_Game, UserInBase
from app.models.task import UserItem
from app.task.Okww.AutoProxy import AutoProxyTask, _OKWW_REL_APP_JSON, _OKWW_REL_EXE


class OkwwUserConfigInitTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary_directory.name)
        self.original_cwd = Path.cwd()
        self.mas_root = self.workspace / "mas"
        self.mas_root.mkdir()
        os.chdir(self.mas_root)
        self.script_root = self.workspace / "ok-ww"
        self.source_config_dir = (
            self.script_root / "data/apps/ok-ww/working/configs"
        )
        self.source_config_dir.mkdir(parents=True)
        (self.source_config_dir / "DailyTask.json").write_text(
            json.dumps({"Which to Farm": "Tacet Suppression"}),
            encoding="utf-8",
        )
        (self.source_config_dir / "Basic Options.json").write_text(
            json.dumps({"Exit App when Game Exits": False}),
            encoding="utf-8",
        )

        self.manager = AppConfig.__new__(AppConfig)
        self.manager.ScriptConfig = MultipleConfig([OkwwConfig])
        self.script_uid, self.script_config = await self.manager.ScriptConfig.add(
            OkwwConfig
        )
        await self.script_config.set("Info", "RootPath", str(self.script_root))

    async def asyncTearDown(self) -> None:
        os.chdir(self.original_cwd)
        self.temporary_directory.cleanup()

    async def test_add_user_initializes_shared_config(self) -> None:
        user_uid, _ = await self.manager.add_user(str(self.script_uid))

        target = (
            self.mas_root
            / "data"
            / str(self.script_uid)
            / "Default"
            / "ConfigFile"
        )
        self.assertTrue((target / "DailyTask.json").is_file())
        self.assertEqual(len(self.script_config.UserData), 1)
        self.assertIn(user_uid, self.script_config.UserData)

    async def test_additional_shared_user_does_not_overwrite_existing_config(
        self,
    ) -> None:
        await self.manager.add_user(str(self.script_uid))
        target_file = (
            self.mas_root
            / "data"
            / str(self.script_uid)
            / "Default"
            / "ConfigFile"
            / "DailyTask.json"
        )
        target_file.write_text(json.dumps({"Customized": True}), encoding="utf-8")
        (self.source_config_dir / "DailyTask.json").write_text(
            json.dumps({"Customized": False}),
            encoding="utf-8",
        )

        await self.manager.add_user(str(self.script_uid))

        self.assertEqual(
            json.loads(target_file.read_text(encoding="utf-8")),
            {"Customized": True},
        )

    async def test_detailed_mode_initializes_user_owned_config(self) -> None:
        user_id = str(uuid.uuid4())

        target = await self.manager.ensure_okww_user_config(
            script_id=str(self.script_uid),
            user_id=user_id,
            mode="详细",
        )

        self.assertEqual(
            target,
            self.mas_root
            / "data"
            / str(self.script_uid)
            / user_id
            / "ConfigFile",
        )
        self.assertTrue((target / "Basic Options.json").is_file())

    async def test_add_user_rolls_back_when_default_config_is_missing(self) -> None:
        for item in self.source_config_dir.iterdir():
            item.unlink()

        with self.assertRaisesRegex(FileNotFoundError, "未找到 OK-WW 默认设置"):
            await self.manager.add_user(str(self.script_uid))

        self.assertEqual(len(self.script_config.UserData), 0)

    async def test_reimport_launcher_refreshes_hidden_game_process_path(self) -> None:
        launcher_root = self.workspace / "launcher"
        launcher_path = launcher_root / "launcher.exe"
        launcher_path.parent.mkdir()
        launcher_path.touch()

        first_game_root = self.workspace / "game-a"
        first_process_path = (
            first_game_root
            / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
        )
        first_process_path.parent.mkdir(parents=True)
        first_process_path.touch()
        self._write_launcher_preference(launcher_root, first_game_root)

        await self.manager.update_script(
            str(self.script_uid),
            {"Game": {"Path": str(launcher_path)}},
        )
        self.assertEqual(
            self.script_config.get("Game", "ProcessPath"),
            first_process_path.resolve().as_posix(),
        )

        second_game_root = self.workspace / "game-b"
        second_process_path = (
            second_game_root
            / "Client/Binaries/Win64/Client-Win64-Shipping.exe"
        )
        second_process_path.parent.mkdir(parents=True)
        second_process_path.touch()
        self._write_launcher_preference(launcher_root, second_game_root)

        await self.manager.update_script(
            str(self.script_uid),
            {"Game": {"Path": str(launcher_path)}},
        )
        self.assertEqual(
            self.script_config.get("Game", "ProcessPath"),
            second_process_path.resolve().as_posix(),
        )

    @staticmethod
    def _write_launcher_preference(launcher_root: Path, game_root: Path) -> None:
        payload = json.dumps({"installDirPath": str(game_root)}).encode("utf-8")
        encoded = base64.b64encode(bytes(value ^ 0x63 for value in payload))
        preference_path = launcher_root / "kr_game_cache/kr_game_temp.bin"
        preference_path.parent.mkdir(exist_ok=True)
        preference_path.write_bytes(encoded)


class OkwwTaskConfigSelfHealTest(unittest.IsolatedAsyncioTestCase):
    async def test_check_ensures_missing_user_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            script_root = Path(temporary_directory)
            (script_root / _OKWW_REL_EXE).touch()
            app_json_path = script_root / _OKWW_REL_APP_JSON
            app_json_path.parent.mkdir(parents=True)
            app_json_path.write_text("{}", encoding="utf-8")

            script_config = OkwwConfig()
            await script_config.set("Info", "RootPath", str(script_root))
            user_config = OkwwUserConfig()
            user_uid = uuid.uuid4()

            task = AutoProxyTask.__new__(AutoProxyTask)
            task.script_config = script_config
            task.cur_user_config = user_config
            task.cur_user_uid = user_uid
            task.cur_user_item = UserItem(
                user_id=str(user_uid),
                name="旧用户",
                status="等待",
            )
            task.script_info = SimpleNamespace(script_id=str(uuid.uuid4()))

            with patch(
                "app.task.Okww.AutoProxy.Config.ensure_okww_user_config",
                new=AsyncMock(),
            ) as ensure_config:
                result = await task.check()

            self.assertEqual(result, "Pass")
            ensure_config.assert_awaited_once_with(
                script_id=task.script_info.script_id,
                user_id=str(user_uid),
                mode="简洁",
            )

    async def test_check_uses_saved_process_path_without_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            script_root = root / "ok-ww"
            (script_root / _OKWW_REL_EXE).parent.mkdir(parents=True)
            (script_root / _OKWW_REL_EXE).touch()
            app_json_path = script_root / _OKWW_REL_APP_JSON
            app_json_path.parent.mkdir(parents=True)
            app_json_path.write_text("{}", encoding="utf-8")

            game_path = root / "Client-Win64-Shipping.exe"
            game_path.touch()
            script_config = OkwwConfig()
            await script_config.set("Info", "RootPath", str(script_root))
            await script_config.set("Game", "Enabled", True)
            await script_config.set("Game", "ProcessPath", str(game_path))

            user_config = OkwwUserConfig()
            user_uid = uuid.uuid4()
            task = AutoProxyTask.__new__(AutoProxyTask)
            task.script_config = script_config
            task.cur_user_config = user_config
            task.cur_user_uid = user_uid
            task.cur_user_item = UserItem(
                user_id=str(user_uid),
                name="用户",
                status="等待",
            )
            task.script_info = SimpleNamespace(script_id=str(uuid.uuid4()))

            with patch(
                "app.task.Okww.AutoProxy.Config.ensure_okww_user_config",
                new=AsyncMock(),
            ):
                result = await task.check()

            self.assertEqual(result, "Pass")


class OkwwAddUserApiErrorTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_defaults_uses_actionable_api_message(self) -> None:
        message = "未找到 OK-WW 默认设置，请先运行一次 OK-WW 并保存设置"
        with patch.object(
            scripts_api.Config,
            "add_user",
            new=AsyncMock(side_effect=FileNotFoundError(message)),
        ):
            response = await scripts_api.add_user(
                UserInBase(scriptId=str(uuid.uuid4()))
            )

        self.assertEqual(response.code, 409)
        self.assertEqual(response.message, message)


class OkwwGameConfigSchemaTest(unittest.TestCase):
    def test_hidden_process_path_is_not_exposed_by_api_schema(self) -> None:
        properties = OkwwConfig_Game.model_json_schema()["properties"]

        self.assertNotIn("ProcessPath", properties)


if __name__ == "__main__":
    unittest.main()
