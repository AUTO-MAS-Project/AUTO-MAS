import asyncio
import errno
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from app.models.ConfigBase import (
    BoolValidator,
    ConfigBase,
    ConfigItem,
    RangeValidator,
)


class SampleConfig(ConfigBase):
    def __init__(self) -> None:
        ## Info -------------------------------------------------------------
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
        ## 配置名称
        self.Info_Name = ConfigItem(
            "Info",
            "Name",
            "默认名称",
            legacy_group="Legacy",
            legacy_name="DisplayName",
        )
        ## 重试次数
        self.Info_RetryCount = ConfigItem("Info", "RetryCount", 1, RangeValidator(0, 3))
        super().__init__()


class ConfigBaseTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "Config.json"
        self.config = SampleConfig()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def read_config(self) -> dict:
        return json.loads(self.config_path.read_text(encoding="utf-8"))

    def default_data(self) -> dict:
        return {
            "Info": {
                "Enabled": False,
                "Name": "默认名称",
                "RetryCount": 1,
            }
        }


class ConfigBaseLifecycleTest(ConfigBaseTestCase):
    async def test_connect_creates_missing_file_with_defaults(self) -> None:
        await self.config.connect(self.config_path)

        self.assertEqual(self.read_config(), self.default_data())
        self.assertEqual(self.config.file, self.config_path)

    async def test_connect_loads_existing_config(self) -> None:
        data = self.default_data()
        data["Info"]["Enabled"] = True
        data["Info"]["Name"] = "已有配置"
        data["Info"]["RetryCount"] = 2
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        await self.config.connect(self.config_path)

        self.assertTrue(self.config.get("Info", "Enabled"))
        self.assertEqual(self.config.get("Info", "Name"), "已有配置")
        self.assertEqual(self.config.get("Info", "RetryCount"), 2)

    async def test_connect_rejects_non_json_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "必须是扩展名为 '.json'"):
            await self.config.connect(self.config_path.with_suffix(".yaml"))

    async def test_load_corrects_invalid_values_and_persists_result(self) -> None:
        self.config.file = self.config_path

        is_dirty = await self.config.load(
            {
                "Info": {
                    "Enabled": "yes",
                    "Name": 123,
                    "RetryCount": 99,
                }
            }
        )

        self.assertTrue(is_dirty)
        self.assertEqual(
            self.read_config(),
            {"Info": {"Enabled": False, "Name": "", "RetryCount": 3}},
        )

    async def test_load_uses_legacy_field_and_persists_current_name(self) -> None:
        self.config.file = self.config_path

        is_dirty = await self.config.load({"Legacy": {"DisplayName": "旧配置名称"}})

        self.assertTrue(is_dirty)
        self.assertEqual(self.config.get("Info", "Name"), "旧配置名称")
        self.assertEqual(self.read_config()["Info"]["Name"], "旧配置名称")
        self.assertNotIn("Legacy", self.read_config())

    async def test_load_returns_false_for_normalized_data(self) -> None:
        is_dirty = await self.config.load(self.default_data())

        self.assertFalse(is_dirty)

    async def test_set_saves_only_when_value_changes(self) -> None:
        self.config.file = self.config_path

        with patch.object(self.config, "save", new_callable=AsyncMock) as save:
            await self.config.set("Info", "Name", "默认名称")
            save.assert_not_awaited()

            await self.config.set("Info", "Name", "新名称")
            save.assert_awaited_once_with()

    async def test_set_runs_each_registered_save_method_once(self) -> None:
        self.config.file = self.config_path
        parent_save = AsyncMock()
        await self.config.add_save_method(parent_save)
        await self.config.add_save_method(parent_save)

        with patch.object(self.config, "save", new_callable=AsyncMock) as save:
            await self.config.set("Info", "Name", "新名称")

        save.assert_awaited_once_with()
        parent_save.assert_awaited_once_with()

    async def test_get_and_set_reject_unknown_item(self) -> None:
        with self.assertRaisesRegex(AttributeError, "Info.Unknown"):
            self.config.get("Info", "Unknown")

        with self.assertRaisesRegex(AttributeError, "Info.Unknown"):
            await self.config.set("Info", "Unknown", "value")

    async def test_lock_blocks_changes_until_unlock(self) -> None:
        await self.config.lock()

        self.assertTrue(self.config.is_locked)
        with self.assertRaisesRegex(ValueError, "配置已锁定"):
            await self.config.set("Info", "Name", "新名称")

        await self.config.unlock()
        await self.config.set("Info", "Name", "新名称")

        self.assertFalse(self.config.is_locked)
        self.assertEqual(self.config.get("Info", "Name"), "新名称")

    async def test_bind_and_unbind_control_change_signal(self) -> None:
        changed = asyncio.Event()
        received_values: list[str] = []

        def receive_value(value: str) -> None:
            received_values.append(value)
            changed.set()

        self.config.bind("Info", "Name", receive_value)
        await self.config.set("Info", "Name", "第一次修改")
        await asyncio.wait_for(changed.wait(), timeout=1)

        self.config.unbind("Info", "Name", receive_value)
        await self.config.set("Info", "Name", "第二次修改")
        await asyncio.sleep(0)

        self.assertEqual(received_values, ["第一次修改"])


class ConfigBaseSaveTest(ConfigBaseTestCase):
    async def test_save_requires_connected_file(self) -> None:
        with self.assertRaisesRegex(ValueError, "文件路径未设置"):
            await self.config.save()

    async def test_save_replaces_config_with_valid_json(self) -> None:
        self.config_path.write_text('{"old": true}', encoding="utf-8")
        self.config.file = self.config_path

        await self.config.save()

        self.assertEqual(self.read_config(), self.default_data())
        self.assertEqual(list(self.config_path.parent.glob("Config.json.tmp")), [])

    async def test_save_keeps_original_config_when_temporary_write_fails(
        self,
    ) -> None:
        original_content = '{"Info": {"Name": "原配置"}}'
        self.config_path.write_text(original_content, encoding="utf-8")
        self.config.file = self.config_path

        def write_partial_then_fail(
            path: Path, data: bytes, encoding: str | None = None
        ) -> None:
            with path.open("wb") as file:
                file.write(data[:1])
            raise OSError(errno.ENOSPC, "No space left on device")

        with patch.object(
            Path,
            "write_bytes",
            autospec=True,
            side_effect=write_partial_then_fail,
        ):
            with self.assertRaisesRegex(OSError, "No space left on device"):
                await self.config.save()

        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original_content)
        self.assertEqual(list(self.config_path.parent.glob("Config.json.tmp")), [])

    async def test_save_keeps_original_config_when_replace_fails(self) -> None:
        original_content = '{"Info": {"Name": "原配置"}}'
        self.config_path.write_text(original_content, encoding="utf-8")
        self.config.file = self.config_path

        with patch.object(
            Path,
            "replace",
            autospec=True,
            side_effect=PermissionError("replace failed"),
        ):
            with self.assertRaisesRegex(PermissionError, "replace failed"):
                await self.config.save()

        self.assertEqual(self.config_path.read_text(encoding="utf-8"), original_content)
        self.assertEqual(list(self.config_path.parent.glob("Config.json.tmp")), [])


if __name__ == "__main__":
    unittest.main()
