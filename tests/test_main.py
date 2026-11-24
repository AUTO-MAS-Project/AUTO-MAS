import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from app.services import telemetry


class MainDevelopmentEnvironmentTest(unittest.TestCase):
    """公共启动环境契约：不依赖目录标记，只有显式 production 才是生产。"""

    def test_default_and_unknown_values_are_development(self) -> None:
        for value in ("", "development", "dev", "unknown"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"AUTO_MAS_ENV": value}):
                    self.assertTrue(main.is_development_environment())
        with patch.dict(os.environ):
            os.environ.pop("AUTO_MAS_ENV", None)
            self.assertTrue(main.is_development_environment())

    def test_explicit_production_ignores_environment_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = Path(temp_dir)
            (repository / ".env").write_text("AUTO_MAS_ENV=development\n", "utf-8")
            with (
                patch.dict(os.environ, {"AUTO_MAS_ENV": " production "}),
                patch.object(main, "current_dir", repository),
            ):
                self.assertFalse(main.is_development_environment())

    def test_hosted_marker_does_not_change_application_environment(self) -> None:
        for value, expected in (("", True), ("production", False)):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ, {"AUTO_MAS_DEV": "1", "AUTO_MAS_ENV": value}
                ):
                    self.assertTrue(main.is_hosted_launch())
                    self.assertIs(main.is_development_environment(), expected)


class ShouldRestartAsAdminTest(unittest.TestCase):
    """提权判断抽成纯函数单独测：main() 直接调用它决定是否 restart_as_admin()，
    避免测试触发 main() 内部真实的 uvicorn 启动。"""

    def test_supervised_never_restarts_regardless_of_other_flags(self) -> None:
        """受监督优先级最高：即便 admin/hosted_launch/development 都不成立也不重启。

        对应受监督场景下真实会发生的情况——非管理员终端下由 Runtime 拉起。
        """

        for admin, hosted_launch, development_environment in (
            (False, False, False),
            (True, False, False),
            (False, True, False),
            (False, False, True),
            (True, True, True),
        ):
            with self.subTest(
                admin=admin,
                hosted_launch=hosted_launch,
                development_environment=development_environment,
            ):
                self.assertFalse(
                    main.should_restart_as_admin(
                        supervised=True,
                        admin=admin,
                        hosted_launch=hosted_launch,
                        development_environment=development_environment,
                    )
                )

    def test_unsupervised_matches_legacy_behavior(self) -> None:
        """未受监督时行为不变：仅当三项判据都不成立才需要提权重启。"""

        cases = [
            ((False, False, False), True),
            ((True, False, False), False),
            ((False, True, False), False),
            ((False, False, True), False),
        ]
        for (admin, hosted_launch, development_environment), expected in cases:
            with self.subTest(
                admin=admin,
                hosted_launch=hosted_launch,
                development_environment=development_environment,
            ):
                self.assertEqual(
                    main.should_restart_as_admin(
                        supervised=False,
                        admin=admin,
                        hosted_launch=hosted_launch,
                        development_environment=development_environment,
                    ),
                    expected,
                )


class TelemetryDevelopmentTest(unittest.TestCase):
    def setUp(self) -> None:
        telemetry._sentry_release = None
        telemetry._sentry_started = False

    tearDown = setUp

    def test_development_environment_skips_sentry(self) -> None:
        with patch.object(telemetry, "_start_sentry") as start_sentry:
            telemetry.init_sentry(release="v0.0.0", development=True, enabled=True)

            start_sentry.assert_not_called()
            self.assertIsNone(telemetry._sentry_release)

    def test_disabled_telemetry_skips_sentry(self) -> None:
        with patch.object(telemetry, "_start_sentry") as start_sentry:
            telemetry.init_sentry(release="v0.0.0", development=False, enabled=False)

            start_sentry.assert_not_called()


def test_sentry_defers_mcp_without_losing_integrations_or_telemetry_toggle(tmp_path):
    """真实 SDK 的冷启动不加载 MCP，加载后的采集在开关切换后仍有效。"""
    root = Path(__file__).resolve().parents[1]
    code = r"""
import json, sys
import sentry_sdk
from sentry_sdk.transport import Transport
from app.services.common import telemetry

events = []
class LocalTransport(Transport):
    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            events.append(event)

original_init = sentry_sdk.init
def init_local(*args, **kwargs):
    if kwargs.get("dsn"):
        kwargs["transport"] = LocalTransport
    return original_init(*args, **kwargs)
sentry_sdk.init = init_local

telemetry.init_sentry(release="v0.0.0", development=False, enabled=True)
expected = {"fastapi", "starlette", "httpx", "logging", "loguru"}
assert expected <= sentry_sdk.get_client().integrations.keys()
assert "mcp" not in sys.modules and "fastapi_mcp" not in sys.modules
sentry_sdk.capture_event({
    "message": "startup check",
    "user": {"id": "PRIVATE_VALUE_FOR_STARTUP_CHECK"},
    "extra": {"value": "PRIVATE_VALUE_FOR_STARTUP_CHECK"},
    "request": {"url": "http://localhost/api/check", "headers": {"authorization": "PRIVATE_VALUE_FOR_STARTUP_CHECK"}},
})
assert len(events) == 1
assert "user" not in events[0] and "extra" not in events[0]
assert "PRIVATE_VALUE_FOR_STARTUP_CHECK" not in json.dumps(events[0])
telemetry.set_telemetry_enabled(False)
assert sentry_sdk.get_client().transport is None
assert "mcp" not in sys.modules
telemetry.set_telemetry_enabled(True)
assert expected <= sentry_sdk.get_client().integrations.keys()
assert "mcp" not in sys.modules

import fastapi_mcp
telemetry.enable_mcp_integration()
assert "mcp" in sentry_sdk.get_client().integrations
telemetry.set_telemetry_enabled(False)
telemetry.enable_mcp_integration()
assert sentry_sdk.get_client().transport is None
telemetry.set_telemetry_enabled(True)
assert expected | {"mcp"} <= sentry_sdk.get_client().integrations.keys()
telemetry.set_telemetry_enabled(False)
print(json.dumps({"ok": True}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(root), "SENTRY_DSN": ""},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {"ok": True}


if __name__ == "__main__":
    unittest.main()
