import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models.config import EmulatorConfig
from app.models.schema import EmulatorConfig as EmulatorConfigSchema


class Emulator2ConfigTest(unittest.IsolatedAsyncioTestCase):
    """Emulator 2.0 配置形态的存取约束。"""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.config_path = Path(self.temporary_directory.name) / "EmulatorConfig.json"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_config(self, data: dict) -> None:
        self.config_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    async def test_emulator2_is_an_accepted_type(self) -> None:
        self.write_config({"Info": {"Type": "emulator2"}})
        config = EmulatorConfig()

        await config.connect(self.config_path)

        self.assertEqual(config.get("Info", "Type"), "emulator2")

    async def test_emulator2_keeps_empty_manager_path(self) -> None:
        """Emulator 2.0 的安装路径写在 Paths 里, Info_Path 保持空串。"""
        self.write_config({"Info": {"Type": "emulator2"}})
        config = EmulatorConfig()

        await config.connect(self.config_path)

        self.assertEqual(config.get("Info", "Path"), "")

    async def test_paths_and_slots_round_trip_as_json(self) -> None:
        paths = [
            {
                "pathId": "p1",
                "installPath": "D:/leidian/LDPlayer14",
                "alias": "主力",
                "type": "ldplayer",
                "version": "14.0.25.1",
            }
        ]
        slots = [
            {"slot": "0", "pathId": "p1", "nativeIndex": "0", "state": "active"},
            {"slot": "1", "pathId": "p1", "nativeIndex": "1", "state": "tombstone"},
        ]
        self.write_config(
            {
                "Info": {
                    "Type": "emulator2",
                    "Paths": json.dumps(paths, ensure_ascii=False),
                    "Slots": json.dumps(slots, ensure_ascii=False),
                }
            }
        )
        config = EmulatorConfig()

        await config.connect(self.config_path)

        self.assertEqual(json.loads(config.get("Info", "Paths")), paths)
        self.assertEqual(json.loads(config.get("Info", "Slots")), slots)

    async def test_paths_and_slots_default_to_empty_list(self) -> None:
        self.write_config({"Info": {"Type": "emulator2"}})
        config = EmulatorConfig()

        await config.connect(self.config_path)

        self.assertEqual(json.loads(config.get("Info", "Paths")), [])
        self.assertEqual(json.loads(config.get("Info", "Slots")), [])


class Emulator2SchemaTest(unittest.TestCase):
    """/api/emulator/get 对所有配置逐条构造 EmulatorConfig 模型。

    只要有一条 Emulator 2.0 配置不被模型接受, 整个接口就会 500,
    连带旧配置一起读不出来。这里锁住那条底线。
    """

    def test_schema_accepts_emulator2_type(self) -> None:
        model = EmulatorConfigSchema(
            **{"Info": {"Name": "新模拟器", "Type": "emulator2", "Path": ""}}
        )

        assert model.Info is not None
        self.assertEqual(model.Info.Type, "emulator2")

    def test_schema_accepts_paths_and_slots(self) -> None:
        model = EmulatorConfigSchema(
            **{
                "Info": {
                    "Type": "emulator2",
                    "Paths": '[{"pathId": "p1"}]',
                    "Slots": '[{"slot": "0"}]',
                }
            }
        )

        assert model.Info is not None
        self.assertEqual(model.Info.Paths, '[{"pathId": "p1"}]')
        self.assertEqual(model.Info.Slots, '[{"slot": "0"}]')

    def test_schema_still_accepts_legacy_types(self) -> None:
        for legacy_type in ("general", "mumu", "ldplayer"):
            with self.subTest(type=legacy_type):
                model = EmulatorConfigSchema(**{"Info": {"Type": legacy_type}})

                assert model.Info is not None
                self.assertEqual(model.Info.Type, legacy_type)


if __name__ == "__main__":
    unittest.main()
