import errno
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.models.ConfigBase import ConfigBase, ConfigItem


class SampleConfig(ConfigBase):
    def __init__(self) -> None:
        self.Info_Name = ConfigItem("Info", "Name", "默认名称")
        super().__init__()


class ConfigBaseSaveTest(unittest.IsolatedAsyncioTestCase):
    async def test_save_replaces_config_with_valid_json(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "Config.json"
            config_path.write_text('{"old": true}', encoding="utf-8")
            config = SampleConfig()
            config.file = config_path

            await config.save()

            self.assertEqual(
                json.loads(config_path.read_text(encoding="utf-8")),
                {"Info": {"Name": "默认名称"}},
            )
            self.assertEqual(list(config_path.parent.glob(".Config.json.*.tmp")), [])

    async def test_save_keeps_original_config_when_temporary_write_fails(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "Config.json"
            original_content = '{"Info": {"Name": "原配置"}}'
            config_path.write_text(original_content, encoding="utf-8")
            config = SampleConfig()
            config.file = config_path

            def write_partial_then_fail(
                path: Path, data: str, encoding: str | None = None
            ) -> None:
                with path.open("w", encoding=encoding) as file:
                    file.write(data[:1])
                raise OSError(errno.ENOSPC, "No space left on device")

            with patch.object(
                Path,
                "write_text",
                autospec=True,
                side_effect=write_partial_then_fail,
            ):
                with self.assertRaisesRegex(OSError, "No space left on device"):
                    await config.save()

            self.assertEqual(config_path.read_text(encoding="utf-8"), original_content)
            self.assertEqual(list(config_path.parent.glob(".Config.json.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
