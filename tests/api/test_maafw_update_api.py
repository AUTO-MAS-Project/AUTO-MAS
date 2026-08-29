import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app.core  # noqa: F401  (initialise app before importing api modules)

from app.api import scripts as scripts_module
from app.api.scripts import update_maafw_project
from app.models.config import MaaFWConfig, SrcConfig
from app.models.schema import MaaFWProjectUpdateIn
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    MaaFWProjectUpdateError,
)
from app.task.MaaFW.tools.core.automas_maafw_project_update.updater import (
    MaaFWProjectUpdateCandidate,
    MaaFWProjectUpdateDiscovery,
    MaaFWProjectUpdateResult,
)


class _FakeInterface:
    def __init__(self, version: str = "1.0.0") -> None:
        self.version = version
        self.name = "Demo"


class _FakeRuntime:
    """Stand-in for ``app.core.Config`` inside the scripts API module."""

    def __init__(self, script_uid: uuid.UUID, script_config) -> None:
        self.ScriptConfig = {script_uid: script_config}
        self.proxy = None


class MaaFWUpdateApiTest(unittest.IsolatedAsyncioTestCase):
    async def _make_script(self, root: Path, *, update=None):
        script_uid = uuid.uuid4()
        config = MaaFWConfig()
        await config.update({"Info": {"Name": "u", "Path": str(root)}})
        if update:
            await config.update({"Update": dict(update)})
        return script_uid, config

    # ---- error paths -------------------------------------------------------

    async def test_rejects_unknown_script(self):
        runtime = _FakeRuntime(uuid.uuid4(), MaaFWConfig())
        with patch.object(scripts_module, "Config", runtime):
            out = await update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=str(uuid.uuid4()), action="check")
            )
        self.assertEqual(out.code, 400)
        self.assertIn("MaaFW 脚本无效", out.message)

    async def test_rejects_cross_type_script(self):
        script_uid = uuid.uuid4()
        runtime = _FakeRuntime(script_uid, SrcConfig())
        with patch.object(scripts_module, "Config", runtime):
            out = await update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
            )
        self.assertEqual(out.code, 400)
        self.assertIn("不是 MaaFW 类型", out.message)

    async def test_rejects_missing_project_path(self):
        script_uid = uuid.uuid4()
        config = MaaFWConfig()
        await config.update({"Info": {"Name": "u"}})
        runtime = _FakeRuntime(script_uid, config)
        with patch.object(scripts_module, "Config", runtime):
            out = await update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
            )
        self.assertEqual(out.code, 400)
        self.assertIn("项目路径", out.message)

    async def test_rejects_non_directory_path(self):
        script_uid = uuid.uuid4()
        config = MaaFWConfig()
        await config.update(
            {"Info": {"Name": "u", "Path": str(Path(tempfile.gettempdir()) / "no-such-dir-xyz")}}
        )
        runtime = _FakeRuntime(script_uid, config)
        with patch.object(scripts_module, "Config", runtime):
            out = await update_maafw_project(
                MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
            )
        self.assertEqual(out.code, 400)
        self.assertIn("不是有效目录", out.message)

    async def test_interface_load_failure_returns_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module,
                "load_interface_model_cached",
                side_effect=scripts_module.MaaFWInterfaceLoadError("坏了"),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 400)
        self.assertIn("interface 读取失败", out.message)
        self.assertIn("坏了", out.message)

    async def test_check_provider_error_surfaces_clean_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface()
            ), patch.object(
                scripts_module,
                "discover_maafw_project_update",
                AsyncMock(side_effect=MaaFWProjectUpdateError("CDK 无效")),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 400)
        self.assertEqual(out.message, "MaaFW 更新检查失败: CDK 无效")

    async def test_apply_provider_error_surfaces_clean_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface()
            ), patch.object(
                scripts_module,
                "update_maafw_project_if_needed",
                AsyncMock(side_effect=MaaFWProjectUpdateError("下载失败")),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="apply")
                )
        self.assertEqual(out.code, 400)
        self.assertEqual(out.message, "MaaFW 项目更新失败: 下载失败")

    # ---- check: version comparison result mapping ------------------------

    async def test_check_reports_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface("2.0.0")
            ), patch.object(
                scripts_module,
                "discover_maafw_project_update",
                AsyncMock(return_value=None),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        self.assertTrue(out.data.checked)
        self.assertFalse(out.data.updateAvailable)
        self.assertEqual(out.data.currentVersion, "2.0.0")

    async def test_check_reports_installable_update(self):
        candidate = MaaFWProjectUpdateCandidate(
            source="github_release", version="2.0.0", download_url="https://x/y.zip"
        )
        discovery = MaaFWProjectUpdateDiscovery(
            source="mirrorchyan", version="2.0.0", candidate=candidate
        )
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface("1.0.0")
            ), patch.object(
                scripts_module,
                "discover_maafw_project_update",
                AsyncMock(return_value=discovery),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        self.assertTrue(out.data.updateAvailable)
        self.assertTrue(out.data.installable)
        self.assertEqual(out.data.latestVersion, "2.0.0")
        self.assertEqual(out.data.source, "github_release")

    async def test_check_reports_version_without_installable_package(self):
        discovery = MaaFWProjectUpdateDiscovery(
            source="mirrorchyan",
            version="2.0.0",
            unavailable_reason="MirrorChyan CDK is required to install this update",
        )
        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(Path(tmp))
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface("1.0.0")
            ), patch.object(
                scripts_module,
                "discover_maafw_project_update",
                AsyncMock(return_value=discovery),
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        self.assertTrue(out.data.updateAvailable)
        self.assertFalse(out.data.installable)
        self.assertIn("CDK", out.message)

    # ---- provider selection: config -> source_config --------------------

    async def test_check_passes_github_source_config_from_update_fields(self):
        captured = {}

        async def _fake_discover(interface, **kwargs):
            captured.update(kwargs)
            return None

        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(
                Path(tmp),
                update={
                    "Source": "GitHub",
                    "Channel": "beta",
                    "GitHubRepo": "owner/repo",
                    "GitHubTag": "v2.0.0",
                    "GitHubAssetPattern": "*win*.zip",
                    "MirrorChyanCDK": "secret-cdk",
                },
            )
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface()
            ), patch.object(
                scripts_module, "discover_maafw_project_update", _fake_discover
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        source_config = captured["source_config"]
        self.assertEqual(source_config["source"], "GitHub")
        self.assertEqual(source_config["package_source"], "GitHub")
        self.assertEqual(source_config["channel"], "beta")
        self.assertEqual(source_config["repo"], "owner/repo")
        self.assertEqual(source_config["tag"], "v2.0.0")
        self.assertEqual(source_config["asset_pattern"], "*win*.zip")
        self.assertEqual(source_config["mirror_cdk"], "secret-cdk")

    async def test_check_injects_shell_hint_for_mfaavalonia_project(self):
        captured = {}

        async def _fake_discover(interface, **kwargs):
            captured.update(kwargs)
            return None

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("MFAAvalonia.dll", "appsettings.json", "interface.json"):
                (root / name).write_text("", encoding="utf-8")
            script_uid, config = await self._make_script(
                root, update={"Source": "GitHub", "GitHubRepo": "owner/repo"}
            )
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface()
            ), patch.object(
                scripts_module, "discover_maafw_project_update", _fake_discover
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        self.assertEqual(
            captured["source_config"].get("project_shell_hint"), "MFAAvalonia"
        )

    async def test_check_omits_shell_hint_for_unrecognised_project(self):
        captured = {}

        async def _fake_discover(interface, **kwargs):
            captured.update(kwargs)
            return None

        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(
                Path(tmp), update={"Source": "GitHub", "GitHubRepo": "owner/repo"}
            )
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface()
            ), patch.object(
                scripts_module, "discover_maafw_project_update", _fake_discover
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="check")
                )
        self.assertEqual(out.code, 200)
        self.assertNotIn("project_shell_hint", captured["source_config"])

    async def test_apply_forwards_update_fields_and_maps_result(self):
        captured = {}

        async def _fake_apply(project_path, interface, **kwargs):
            captured.update(kwargs)
            return MaaFWProjectUpdateResult(
                checked=True,
                updated=True,
                current_version="1.0.0",
                latest_version="2.0.0",
                source="mirrorchyan",
                update_available=True,
                installable=True,
                message="MaaFW 项目更新完成: 2.0.0",
            )

        with tempfile.TemporaryDirectory() as tmp:
            script_uid, config = await self._make_script(
                Path(tmp), update={"Source": "MirrorChyan", "MirrorChyanCDK": "cdk-1"}
            )
            runtime = _FakeRuntime(script_uid, config)
            with patch.object(scripts_module, "Config", runtime), patch.object(
                scripts_module, "load_interface_model_cached", return_value=_FakeInterface("1.0.0")
            ), patch.object(
                scripts_module, "update_maafw_project_if_needed", _fake_apply
            ):
                out = await update_maafw_project(
                    MaaFWProjectUpdateIn(scriptId=str(script_uid), action="apply")
                )
        self.assertEqual(out.code, 200)
        self.assertTrue(out.data.updated)
        self.assertEqual(out.data.latestVersion, "2.0.0")
        self.assertEqual(captured["source"], "MirrorChyan")
        self.assertEqual(captured["mirror_cdk"], "cdk-1")
        self.assertIsNone(captured["proxy"])


if __name__ == "__main__":
    unittest.main()
