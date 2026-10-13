"""配置文件损坏时保留 .corrupt-* 副本后按默认值加载; save 串行落盘且顺序与调用顺序一致。"""

import asyncio
import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.models.ConfigBase import BoolValidator, ConfigBase, ConfigItem, MultipleConfig


class SampleConfig(ConfigBase):
    def __init__(self) -> None:
        ## 是否启用
        self.Info_Enabled = ConfigItem("Info", "Enabled", False, BoolValidator())
        super().__init__()


class CorruptConfigFileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.config_path = self.root / "Config.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _corrupt_copies(self) -> list[Path]:
        return sorted(self.root.glob("Config.json.corrupt-*"))

    async def test_corrupt_json_keeps_copy_and_loads_defaults(self) -> None:
        self.config_path.write_text('{"Info": {"Enabled": tru', encoding="utf-8")
        config = SampleConfig()

        await config.connect(self.config_path)

        copies = self._corrupt_copies()
        self.assertEqual(len(copies), 1)
        self.assertEqual(
            copies[0].read_text(encoding="utf-8"), '{"Info": {"Enabled": tru'
        )
        self.assertFalse(config.get("Info", "Enabled"))

    async def test_empty_file_is_not_treated_as_corrupt(self) -> None:
        self.config_path.touch()
        config = SampleConfig()

        await config.connect(self.config_path)

        self.assertEqual(self._corrupt_copies(), [])
        self.assertFalse(config.get("Info", "Enabled"))

    async def test_multiple_config_corrupt_json_keeps_copy(self) -> None:
        self.config_path.write_text("[not json", encoding="utf-8")
        config = MultipleConfig([SampleConfig])

        await config.connect(self.config_path)

        self.assertEqual(len(self._corrupt_copies()), 1)
        self.assertEqual(len(config), 0)

    async def test_valid_json_still_loads_normally(self) -> None:
        self.config_path.write_text(
            json.dumps({"Info": {"Enabled": True}}), encoding="utf-8"
        )
        config = SampleConfig()

        await config.connect(self.config_path)

        self.assertEqual(self._corrupt_copies(), [])
        self.assertTrue(config.get("Info", "Enabled"))


class SerializedSaveTest(unittest.IsolatedAsyncioTestCase):
    async def test_consecutive_saves_land_in_call_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = SampleConfig()
            await config.connect(Path(temp_dir) / "Config.json")
            written: list[bool] = []
            delays = iter([0.05])

            def slow_write(path, payload, **kwargs):
                # 第一次写盘故意更慢: 若不串行, 后一次会先落盘, 旧数据覆盖新数据
                time.sleep(next(delays, 0.0))
                written.append(payload["Info"]["Enabled"])

            with patch("app.models.ConfigBase.write_file", side_effect=slow_write):
                config.Info_Enabled.setValue(True)
                first = asyncio.create_task(config.save())
                await asyncio.sleep(0)
                config.Info_Enabled.setValue(False)
                second = asyncio.create_task(config.save())
                await asyncio.gather(first, second)

            self.assertEqual(written, [True, False])
