"""分享通用脚本配置前的隐私脱敏与风险检查。

自动脱敏只覆盖已知的路径配置项，命令行参数、日志规则这类自由文本仍可能带出账号、
密码、令牌或本机绝对路径，必须被 scan_privacy_risks 挑出来交给用户确认。
"""

import unittest
from pathlib import Path

from app.core import Config


def _risk_fields(config: dict) -> set[str]:
    return {risk["field"] for risk in Config.scan_privacy_risks(config)}


class MaskHomePathTest(unittest.TestCase):
    def test_replaces_home_directory_in_both_separators(self) -> None:
        home = str(Path.home())

        self.assertEqual(
            Config._mask_home_path(f"{home}\\Scripts\\run.exe"),
            "%USERPROFILE%\\Scripts\\run.exe",
        )
        self.assertEqual(
            Config._mask_home_path(f"{home.replace(chr(92), '/')}/Scripts/run.exe"),
            "%USERPROFILE%/Scripts/run.exe",
        )

    def test_keeps_unrelated_value(self) -> None:
        self.assertEqual(Config._mask_home_path("--headless"), "--headless")

    def test_does_not_cut_a_longer_sibling_directory(self) -> None:
        home = str(Path.home())

        # C:\\Users\\qiyin 不应该把 C:\\Users\\qiyinxi 切掉一截
        self.assertEqual(
            Config._mask_home_path(f"{home}xi\\run.exe"), f"{home}xi\\run.exe"
        )


class ScanPrivacyRisksTest(unittest.TestCase):
    def test_placeholder_paths_are_not_reported(self) -> None:
        config = {
            "Info": {"Name": "示例", "RootPath": "C:\\脚本根目录"},
            "Script": {
                "ScriptPath": "C:\\脚本根目录\\run.exe",
                "ConfigPath": "%APPDATA%/demo/config.json",
                "Arguments": "--config %USERPROFILE%/demo.json",
            },
        }

        self.assertEqual(_risk_fields(config), set())

    def test_reports_credential_like_arguments(self) -> None:
        config = {
            "Script": {
                "Arguments": "--token=abcdef123456",
                "TrackProcessCmdline": "--password: hunter2",
                "LogPathFormat": "--api-key abcdef",
            }
        }

        self.assertEqual(
            _risk_fields(config),
            {"Script.Arguments", "Script.TrackProcessCmdline", "Script.LogPathFormat"},
        )

    def test_reports_credentials_embedded_in_url(self) -> None:
        config = {"Game": {"URL": "https://alice:s3cret@example.com/launch"}}

        self.assertEqual(_risk_fields(config), {"Game.URL"})

    def test_reports_remaining_absolute_path(self) -> None:
        config = {"Game": {"Path": "D:\\Games\\demo\\launcher.exe"}}

        self.assertEqual(_risk_fields(config), {"Game.Path"})

    def test_reports_local_user_name(self) -> None:
        user_name = Path.home().name
        if len(user_name) <= 2:
            self.skipTest("本机用户名过短, 不参与匹配")

        config = {"Script": {"LogPathFormat": f"logs-{user_name}-%Y-%m-%d"}}

        self.assertEqual(_risk_fields(config), {"Script.LogPathFormat"})

    def test_plain_url_is_not_an_absolute_path(self) -> None:
        # https:// 里的 s:/ 不是盘符，通用脚本的 Game.URL 是正式字段，不该每次都被报风险
        config = {
            "Game": {"URL": "https://example.com/launch"},
            "Script": {"Arguments": "--url http://127.0.0.1:8000/start"},
        }

        self.assertEqual(_risk_fields(config), set())

    def test_ignores_empty_and_non_string_values(self) -> None:
        config = {
            "Script": {"Arguments": "", "LogTimeStart": 1, "IfTrackProcess": False},
            "SubConfigsInfo": None,
        }

        self.assertEqual(_risk_fields(config), set())


if __name__ == "__main__":
    unittest.main()
