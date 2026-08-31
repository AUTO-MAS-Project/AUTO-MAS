import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.api.scripts import preview_maafw_interface
from app.models.schema import (
    MaaFWConfig,
    MaaFWConfig_Info,
    MaaFWConfig_Run,
    MaaFWConfig_Selection,
    MaaFWInterfacePreviewData,
    MaaFWInterfacePreviewIn,
    MaaFWInterfacePreviewOut,
    MaaFWUserConfig,
    ScriptCreateIn,
    ScriptCreateOut,
    ScriptGetOut,
    ScriptIndexItem,
    ScriptUpdateIn,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.loader import (
    load_interface_model,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.preview import (
    build_interface_preview_data,
)


INTERFACE = {
    "interface_version": 2,
    "name": "preview-demo",
    "label": "Preview Demo",
    "controller": [{"name": "安卓端", "type": "Adb"}],
    "resource": [{"name": "简中", "path": ["./resource"]}],
    "task": [{"name": "Main", "entry": "main", "default_check": True}],
    "import": ["fragments/tasks.json"],
}
FRAGMENT = {
    "task": [{"name": "Imported", "entry": "imported"}],
}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class MaaFWInterfacePreviewTest(unittest.TestCase):
    def test_load_interface_preview_merges_imported_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "interface.json", INTERFACE)
            _write_json(root / "fragments" / "tasks.json", FRAGMENT)

            interface = load_interface_model(root)
            preview = build_interface_preview_data(root, interface)
            data = MaaFWInterfacePreviewData.model_validate(
                preview.model_dump(mode="json")
            )

            self.assertEqual([task.name for task in data.tasks], ["Main", "Imported"])
            self.assertEqual(data.controllers[0].name, "安卓端")
            self.assertEqual(data.resources[0].name, "简中")
            self.assertEqual(data.importCount, 1)

    def test_preview_api_returns_success_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_json(root / "interface.json", INTERFACE)
            _write_json(root / "fragments" / "tasks.json", FRAGMENT)

            result = asyncio.run(
                preview_maafw_interface(MaaFWInterfacePreviewIn(path=str(root)))
            )

            self.assertIsInstance(result, MaaFWInterfacePreviewOut)
            self.assertEqual(result.code, 200)
            self.assertEqual(result.status, "success")
            self.assertIsNotNone(result.data)
            self.assertEqual(len(result.data.tasks), 2)
            self.assertIn("共 2 个任务", result.message)

    def test_preview_api_returns_error_envelope_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_root = Path(temp_dir) / "missing"
            result = asyncio.run(
                preview_maafw_interface(MaaFWInterfacePreviewIn(path=str(missing_root)))
            )

            self.assertEqual(result.code, 400)
            self.assertEqual(result.status, "error")
            self.assertIsNone(result.data)
            self.assertIn("项目目录", result.message)
            self.assertNotIn("Traceback", result.message)

    def test_preview_api_maps_unexpected_error_to_safe_envelope(self) -> None:
        with patch(
            "app.api.scripts.load_interface_model_cached",
            side_effect=RuntimeError("internal detail"),
        ):
            result = asyncio.run(
                preview_maafw_interface(MaaFWInterfacePreviewIn(path="C:/project"))
            )

        self.assertEqual(result.code, 500)
        self.assertEqual(result.status, "error")
        self.assertIsNone(result.data)
        self.assertIn("MFW interface 预览失败", result.message)
        self.assertIn("internal detail", result.message)
        self.assertNotIn("Traceback", result.message)

    def test_maafw_script_contracts_parse(self) -> None:
        script_id = "maafw-script"
        config = MaaFWConfig(
            Info=MaaFWConfig_Info(Name="本地项目", Path="C:/project"),
            Run=MaaFWConfig_Run(RunTimeLimit=42),
            Selection=MaaFWConfig_Selection(
                Controller='["安卓端"]',
                Resource='["简中"]',
                Tasks='["启动游戏"]',
            ),
        )

        self.assertEqual(ScriptCreateIn(type="MaaFW").type, "MaaFW")
        create_out = ScriptCreateOut(scriptId=script_id, data=config)
        self.assertIsInstance(create_out.data, MaaFWConfig)
        index = ScriptIndexItem(uid=script_id, type="MaaFWConfig")
        get_out = ScriptGetOut(index=[index], data={script_id: config})
        update_in = ScriptUpdateIn(scriptId=script_id, data=config)

        self.assertEqual(get_out.index[0].type, "MaaFWConfig")
        self.assertIsInstance(get_out.data[script_id], MaaFWConfig)
        self.assertIsInstance(update_in.data, MaaFWConfig)
        self.assertEqual(
            MaaFWUserConfig.model_validate({"Info": {"Name": "用户"}}).Info.Name,
            "用户",
        )


if __name__ == "__main__":
    unittest.main()
