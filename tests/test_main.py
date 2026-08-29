import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
from app.services import telemetry


class MainDevelopmentEnvironmentTest(unittest.TestCase):
    def test_explicit_development_environment(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_ENV": "development"}):
            self.assertTrue(main.is_development_environment())

    def test_repository_checkout_is_development_environment(self) -> None:
        """源码仓库带 .env 标记文件，任意解释器直接启动都算开发环境。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = Path(temp_dir)
            (repository / ".git").mkdir()
            (repository / ".env").write_text("AUTO_MAS_ENV=development\n", "utf-8")

            with (
                patch.dict(os.environ, {"AUTO_MAS_ENV": ""}),
                patch.object(main, "current_dir", repository),
            ):
                self.assertTrue(main.is_development_environment())

    def test_user_installation_is_not_development(self) -> None:
        """用户安装目录同样带 .git，但不含 .env，应视为生产环境。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            application_dir = Path(temp_dir)
            (application_dir / ".git").mkdir()

            with (
                patch.dict(os.environ, {"AUTO_MAS_ENV": ""}),
                patch.object(main, "current_dir", application_dir),
            ):
                self.assertFalse(main.is_development_environment())

    def test_hosted_launch_is_not_development(self) -> None:
        """前端拉起的打包版后端只跳过提权，不应被判定为开发环境。"""

        with tempfile.TemporaryDirectory() as temp_dir:
            application_dir = Path(temp_dir)
            (application_dir / ".git").mkdir()

            with (
                patch.dict(os.environ, {"AUTO_MAS_DEV": "1", "AUTO_MAS_ENV": ""}),
                patch.object(main, "current_dir", application_dir),
            ):
                self.assertTrue(main.is_hosted_launch())
                self.assertFalse(main.is_development_environment())

    def test_direct_launch_is_not_hosted(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_DEV": ""}):
            self.assertFalse(main.is_hosted_launch())


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

    def test_development_environment_ignores_later_toggle(self) -> None:
        """开发环境下用户打开遥测开关同样不应启动 Sentry。"""

        with patch.object(telemetry, "_start_sentry") as start_sentry:
            telemetry.init_sentry(release="v0.0.0", development=True, enabled=True)
            telemetry.set_telemetry_enabled(True)

            start_sentry.assert_not_called()

    def test_production_environment_starts_sentry(self) -> None:
        with patch.object(telemetry, "_start_sentry") as start_sentry:
            telemetry.init_sentry(release="v0.0.0", development=False, enabled=True)

            start_sentry.assert_called_once_with("v0.0.0")

    def test_disabled_telemetry_skips_sentry(self) -> None:
        with patch.object(telemetry, "_start_sentry") as start_sentry:
            telemetry.init_sentry(release="v0.0.0", development=False, enabled=False)

            start_sentry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
