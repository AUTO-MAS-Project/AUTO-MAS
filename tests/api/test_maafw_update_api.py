"""``POST /api/scripts/maafw/update`` 的 API 侧契约测试（mock 核心更新包）。

覆盖：脚本级 / 全局 CDK 与 channel 的兜底、source_config 不再携带 GitHub 高级
参数、核心包返回的 CDK 状态字段映射到响应、CDK 异常不算错误、响应与日志里
不出现 CDK 明文。
"""

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import app.api.scripts as scripts_api
from app.models.schema import MaaFWProjectUpdateIn
from app.task.MaaFW.tools.core.automas_maafw_project_update import (
    MaaFWProjectUpdateResult,
)

SECRET_CDK = "0001bf520b5a763d3e61f460"
GLOBAL_CDK = "0001bf520ae489bd534c697e"
GITHUB_KEYS = {"repo", "tag", "asset_pattern", "token", "source", "package_source"}


class _FakeConfig:
    """模拟 ``ConfigBase.get``：缺项抛 AttributeError，与真实行为一致。"""

    def __init__(self, values: dict[tuple[str, str], object], proxy=None):
        self._values = values
        self.proxy = proxy

    def get(self, group: str, name: str):
        if (group, name) not in self._values:
            raise AttributeError(f"配置项 '{group}.{name}' 不存在")
        return self._values[(group, name)]


class _LogSink:
    def __init__(self):
        self.lines: list[str] = []

    def info(self, message, *args, **kwargs):
        self.lines.append(str(message))

    warning = error = debug = info


class MaaFWUpdateApiTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project_dir = self._tmp.name
        self.interface = SimpleNamespace(version="v1.0.0", mirrorchyan_rid="Demo")
        self.log_sink = _LogSink()
        self.discover = AsyncMock(return_value=None)
        self.apply = AsyncMock(
            return_value=MaaFWProjectUpdateResult(
                checked=True, updated=False, current_version="v1.0.0"
            )
        )

    def tearDown(self):
        self._tmp.cleanup()

    def _script_config(self, cdk: str = "", channel: str = "") -> _FakeConfig:
        return _FakeConfig(
            {
                ("Info", "Path"): self.project_dir,
                ("Update", "MirrorChyanCDK"): cdk,
                ("Update", "Channel"): channel,
                # 旧的 GitHub 高级参数即使还留在配置里也不得被 API 读取。
                ("Update", "Source"): "GitHub",
                ("Update", "GitHubRepo"): "owner/repo",
                ("Update", "GitHubTag"): "v9",
                ("Update", "GitHubAssetPattern"): "*.zip",
            }
        )

    def _patches(self, script_config, global_config):
        return [
            patch.object(
                scripts_api, "_maafw_script_config", return_value=script_config
            ),
            patch.object(scripts_api, "Config", global_config),
            patch.object(
                scripts_api, "load_interface_model_cached", return_value=self.interface
            ),
            patch.object(
                scripts_api, "detect_maafw_project_shell_hint", return_value=""
            ),
            patch.object(scripts_api, "discover_maafw_project_update", self.discover),
            patch.object(scripts_api, "update_maafw_project_if_needed", self.apply),
            patch.object(scripts_api, "_maafw_update_logger", self.log_sink),
        ]

    async def _call(
        self,
        action,
        *,
        script_cdk="",
        script_channel="",
        global_cdk="",
        global_channel="",
    ):
        script_config = self._script_config(script_cdk, script_channel)
        global_config = _FakeConfig(
            {
                ("Update", "MirrorChyanCDK"): global_cdk,
                ("Update", "Channel"): global_channel,
            }
        )
        patches = self._patches(script_config, global_config)
        for p in patches:
            p.start()
        try:
            return await scripts_api.update_maafw_project(
                MaaFWProjectUpdateIn(scriptId="script-1", action=action)
            )
        finally:
            for p in reversed(patches):
                p.stop()

    def _check_source_config(self) -> dict:
        self.discover.assert_awaited_once()
        return self.discover.await_args.kwargs["source_config"]

    # ---- CDK / channel 兜底 -------------------------------------------------

    async def test_check_blank_script_cdk_falls_back_to_global(self):
        result = await self._call("check", script_cdk="", global_cdk=GLOBAL_CDK)
        self.assertEqual(result.code, 200)
        self.assertEqual(self._check_source_config()["mirror_cdk"], GLOBAL_CDK)

    async def test_check_script_cdk_wins_over_global(self):
        await self._call("check", script_cdk=SECRET_CDK, global_cdk=GLOBAL_CDK)
        self.assertEqual(self._check_source_config()["mirror_cdk"], SECRET_CDK)

    async def test_check_both_blank_passes_empty_cdk_and_stable_channel(self):
        await self._call("check")
        source_config = self._check_source_config()
        self.assertEqual(source_config["mirror_cdk"], "")
        self.assertEqual(source_config["channel"], "stable")

    async def test_check_channel_falls_back_script_then_global(self):
        await self._call("check", global_channel="beta")
        self.assertEqual(self._check_source_config()["channel"], "beta")
        self.discover.reset_mock()
        await self._call("check", script_channel="alpha", global_channel="beta")
        self.assertEqual(self._check_source_config()["channel"], "alpha")

    async def test_apply_blank_script_cdk_falls_back_to_global(self):
        result = await self._call(
            "apply", global_cdk=GLOBAL_CDK, global_channel="beta"
        )
        self.assertEqual(result.code, 200)
        self.apply.assert_awaited_once()
        kwargs = self.apply.await_args.kwargs
        self.assertEqual(kwargs["mirror_cdk"], GLOBAL_CDK)
        self.assertEqual(kwargs["channel"], "beta")

    async def test_apply_both_blank_passes_empty_cdk(self):
        await self._call("apply")
        kwargs = self.apply.await_args.kwargs
        self.assertEqual(kwargs["mirror_cdk"], "")
        self.assertEqual(kwargs["channel"], "stable")

    # ---- 不再传 GitHub 高级参数 --------------------------------------------

    async def test_source_config_has_no_github_keys(self):
        await self._call("check", script_cdk=SECRET_CDK)
        source_config = self._check_source_config()
        self.assertEqual(set(source_config) & GITHUB_KEYS, set())
        self.assertLessEqual(
            set(source_config), {"mirror_cdk", "channel", "project_shell_hint"}
        )

    async def test_apply_does_not_pass_github_kwargs(self):
        await self._call("apply", script_cdk=SECRET_CDK)
        kwargs = self.apply.await_args.kwargs
        for name in ("source", "github_repo", "github_tag", "github_asset_pattern"):
            self.assertNotIn(name, kwargs)
        self.assertNotIn("source_config", kwargs)

    # ---- 响应字段映射 ------------------------------------------------------

    async def test_check_response_maps_core_fields(self):
        self.discover.return_value = SimpleNamespace(
            source="mirrorchyan",
            version="v1.1.0",
            candidate=None,
            installable=False,
            unavailable_reason="",
            version_name="v1.1.0",
            cdk_status="ok",
            cdk_message="",
            cdk_expired_time=1801411200,
            skipped_reason=None,
        )
        result = await self._call("check", script_cdk=SECRET_CDK)
        self.assertEqual(result.code, 200)
        data = result.data
        self.assertTrue(data.updateAvailable)
        self.assertEqual(data.latestVersion, "v1.1.0")
        self.assertEqual(data.versionName, "v1.1.0")
        self.assertEqual(data.cdkStatus, "ok")
        self.assertIsNone(data.cdkMessage)
        self.assertEqual(data.cdkExpiredTime, 1801411200)
        self.assertEqual(data.source, "mirrorchyan")
        self.assertIsNone(data.skippedReason)
        self.assertNotIn("（", result.message)

    async def test_check_quota_cdk_is_success_with_message(self):
        quota_text = "CDK 今日下载次数已用尽"
        self.discover.return_value = SimpleNamespace(
            source="mirrorchyan",
            version="v1.1.0",
            candidate=SimpleNamespace(source="github", installable=True),
            installable=True,
            unavailable_reason="",
            version_name="v1.1.0",
            cdk_status="quota",
            cdk_message=quota_text,
            cdk_expired_time=None,
            skipped_reason=None,
        )
        result = await self._call("check", script_cdk=SECRET_CDK)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.status, "success")
        self.assertEqual(result.data.cdkStatus, "quota")
        self.assertEqual(result.data.cdkMessage, quota_text)
        self.assertIn(quota_text, result.message)
        self.assertEqual(result.data.source, "github")

    async def test_check_tolerates_core_without_cdk_fields(self):
        # 核心包未补齐 §8 字段（或旧版本）时，discovery 对象上根本没有这些属性。
        self.discover.return_value = SimpleNamespace(
            source="mirrorchyan",
            version="v1.1.0",
            candidate=None,
            installable=False,
            unavailable_reason="",
        )
        result = await self._call("check")
        self.assertEqual(result.code, 200)
        data = result.data
        self.assertEqual(data.latestVersion, "v1.1.0")
        self.assertIsNone(data.cdkStatus)
        self.assertIsNone(data.cdkMessage)
        # versionName 由 discovery.version 补齐，前端总能拿到最新版本名。
        self.assertEqual(data.versionName, "v1.1.0")
        self.assertIsNone(data.cdkExpiredTime)
        self.assertIsNone(data.skippedReason)

    async def test_apply_maps_core_fields_and_expired_cdk_message(self):
        expired_text = "CDK 已过期"
        self.apply.return_value = SimpleNamespace(
            checked=True,
            updated=True,
            update_available=True,
            installable=True,
            current_version="v1.0.0",
            latest_version="v1.1.0",
            previous_version="v1.0.0",
            version_name="v1.1.0",
            source="github",
            cdk_status="expired",
            cdk_message=expired_text,
            cdk_expired_time=None,
            message="MaaFW 项目更新完成: v1.1.0",
            skipped_reason=None,
        )
        result = await self._call("apply", script_cdk=SECRET_CDK)
        self.assertEqual(result.code, 200)
        self.assertEqual(result.status, "success")
        self.assertIn(expired_text, result.message)
        self.assertIn("MaaFW 项目更新完成: v1.1.0", result.message)
        data = result.data
        self.assertTrue(data.updated)
        self.assertEqual(data.currentVersion, "v1.0.0")
        self.assertEqual(data.latestVersion, "v1.1.0")
        self.assertEqual(data.versionName, "v1.1.0")
        self.assertEqual(data.source, "github")
        self.assertEqual(data.cdkStatus, "expired")
        self.assertEqual(data.cdkMessage, expired_text)

    async def test_apply_maps_skipped_reason(self):
        self.apply.return_value = SimpleNamespace(
            updated=False,
            previous_version="v1.0.0",
            version_name="v1.0.0",
            source=None,
            cdk_status="absent",
            cdk_message="",
            cdk_expired_time=None,
            message="已是最新版本",
            skipped_reason="already latest",
        )
        result = await self._call("apply")
        self.assertEqual(result.code, 200)
        self.assertEqual(result.message, "已是最新版本")
        self.assertEqual(result.data.skippedReason, "already latest")
        self.assertEqual(result.data.cdkStatus, "absent")
        self.assertEqual(result.data.currentVersion, "v1.0.0")
        self.assertFalse(result.data.updated)

    # ---- CDK 不得明文出现 --------------------------------------------------

    async def test_cdk_never_appears_in_response_or_logs(self):
        async def _leaky_apply(*args, **kwargs):
            send_log = kwargs["send_log"]
            cdk = kwargs["mirror_cdk"]
            send_log(f"cdk={cdk}")
            send_log('{"cdk": "' + cdk + '"}')
            return MaaFWProjectUpdateResult(
                checked=True, updated=False, current_version="v1.0.0"
            )

        self.apply.side_effect = _leaky_apply
        result = await self._call("apply", script_cdk=SECRET_CDK)
        self.assertEqual(result.code, 200)
        self.assertNotIn(SECRET_CDK, result.model_dump_json())
        self.assertTrue(self.log_sink.lines, "endpoint should have logged")
        for line in self.log_sink.lines:
            self.assertNotIn(SECRET_CDK, line)


if __name__ == "__main__":
    unittest.main()
