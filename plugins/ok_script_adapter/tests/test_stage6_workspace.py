from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import UUID

from app.plugins.frontend_extensions import PluginFrontendManifest
from ok_script_adapter.plugin import _workspace_target_projection


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PLUGIN_ROOT / "src" / "ok_script_adapter"
FRONTEND_ROOT = PACKAGE_ROOT / "frontend"


class WorkspaceTargetProjectionTest(unittest.TestCase):
    def test_projection_only_returns_workspace_selection_metadata(self) -> None:
        script_id = UUID("11111111-1111-1111-1111-111111111111")
        user_id = UUID("22222222-2222-2222-2222-222222222222")

        target = _workspace_target_projection(
            script_uid=script_id,
            script_form={
                "Info": {
                    "Name": "明日方舟终末地",
                    "ProjectLabel": "明日方舟终末地",
                    "ResourceName": "ok-ef",
                    "RootPath": "E:/games/ok-ef",
                    "SensitiveValue": "must-not-leak",
                },
                "Notify": {"ServerChanKey": "must-not-leak"},
            },
            users=[
                (
                    user_id,
                    {
                        "Info": {"Name": "默认用户", "Status": False},
                        "Notify": {"Password": "must-not-leak"},
                    },
                )
            ],
        )

        self.assertEqual(target["id"], str(script_id))
        self.assertEqual(target["name"], "明日方舟终末地")
        self.assertEqual(target["projectLabel"], "明日方舟终末地")
        self.assertEqual(target["resourceName"], "ok-ef")
        self.assertTrue(target["rootConfigured"])
        self.assertEqual(
            target["users"],
            [{"id": str(user_id), "name": "默认用户", "enabled": False}],
        )

        serialized = json.dumps(target, ensure_ascii=False)
        self.assertNotIn("E:/games/ok-ef", serialized)
        self.assertNotIn("must-not-leak", serialized)
        self.assertNotIn("SensitiveValue", serialized)


class WorkspaceFrontendPackageTest(unittest.TestCase):
    def test_manifest_and_resources_follow_custom_element_contract(self) -> None:
        manifest_path = FRONTEND_ROOT / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = PluginFrontendManifest.model_validate(manifest_data)

        self.assertEqual(manifest.renderer, "custom-element")
        self.assertEqual(manifest.entry, "frontend/index.js")
        self.assertEqual(manifest.style, ["frontend/index.css"])
        self.assertEqual(
            [element.tag for element in manifest.elements],
            ["auto-mas-ok-script-workspace"],
        )
        self.assertTrue((FRONTEND_ROOT / "index.js").is_file())
        self.assertTrue((FRONTEND_ROOT / "index.css").is_file())

    def test_package_data_and_page_registration_are_declared(self) -> None:
        pyproject = (PLUGIN_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        plugin_source = (PACKAGE_ROOT / "plugin.py").read_text(encoding="utf-8")

        self.assertIn('ok_script_adapter = ["frontend/*.json", "frontend/*.js", "frontend/*.css"]', pyproject)
        self.assertIn('id="ok-script-workspace"', plugin_source)
        self.assertIn('path="/ok-script/workspace"', plugin_source)
        self.assertIn('renderer="custom-element"', plugin_source)
        self.assertIn('element_tag="auto-mas-ok-script-workspace"', plugin_source)
        self.assertIn('"/ok-script/workspace/targets"', plugin_source)

    def test_entry_uses_public_api_and_cleans_up_element_resources(self) -> None:
        entry = (FRONTEND_ROOT / "index.js").read_text(encoding="utf-8")
        styles = (FRONTEND_ROOT / "index.css").read_text(encoding="utf-8")

        self.assertIn("window.pluginAPI", entry)
        self.assertIn("ok-script/workspace/targets", entry)
        self.assertIn("ok-script/configs/list", entry)
        self.assertIn("ok-script/configs/batch-update", entry)
        self.assertIn("disconnectedCallback()", entry)
        self.assertIn("this._listenerController?.abort()", entry)
        self.assertNotIn("innerHTML", entry)
        self.assertIn("auto-mas-ok-script-workspace", styles)
        self.assertNotIn("body {", styles)


if __name__ == "__main__":
    unittest.main()
