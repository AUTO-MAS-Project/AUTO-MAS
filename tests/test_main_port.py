import os
import unittest
from unittest.mock import patch

import main


class ResolveHttpPortTest(unittest.TestCase):
    """端口解析用例单独成文件：本模块只依赖 main，不触发 app.services 的循环导入。"""

    def test_production_keeps_legacy_port(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": ""}):
            self.assertEqual(main.resolve_http_port(False), main.DEFAULT_HTTP_PORT)

    def test_development_uses_dedicated_port(self) -> None:
        """开发环境错开端口，用户已装正式版仍可同时运行。"""

        with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": ""}):
            self.assertEqual(main.resolve_http_port(True), main.DEV_HTTP_PORT)

    def test_environment_variable_overrides_both(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": "40000"}):
            self.assertEqual(main.resolve_http_port(True), 40000)
            self.assertEqual(main.resolve_http_port(False), 40000)

    def test_invalid_environment_variable_falls_back(self) -> None:
        for raw in ("0", "70000", "abc"):
            with self.subTest(raw=raw):
                with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": raw}):
                    self.assertEqual(
                        main.resolve_http_port(False), main.DEFAULT_HTTP_PORT
                    )

    def test_supervised_uses_injected_port_ignoring_dev_and_override(self) -> None:
        """受监督模式只认 AUTO_MAS_SUPERVISED_PORT：开发环境判据与 AUTO_MAS_HTTP_PORT 均不生效。

        AUTO-MAS-Runtime 按实例类型选端口（managed 36163 / development 36164）
        并据此做健康检查；后端若钉死 36163，受监督的开发版会撞上同机正在运行的
        正式版。宿主环境残留的 .env / AUTO_MAS_ENV=development 或历史
        AUTO_MAS_HTTP_PORT 也不能把端口从注入值上带偏。
        """

        with patch.dict(
            os.environ,
            {
                "AUTO_MAS_SUPERVISED": "1",
                "AUTO_MAS_SUPERVISED_PORT": "36164",
                "AUTO_MAS_ENV": "development",
                "AUTO_MAS_HTTP_PORT": "40000",
            },
        ):
            self.assertEqual(main.resolve_http_port(True), 36164)
            self.assertEqual(main.resolve_http_port(False), 36164)

    def test_supervised_falls_back_to_default_port_when_not_injected(self) -> None:
        """旧版 Runtime 不注入 AUTO_MAS_SUPERVISED_PORT 时回退 36163，且仍忽略 AUTO_MAS_HTTP_PORT。"""

        with patch.dict(
            os.environ,
            {
                "AUTO_MAS_SUPERVISED": "1",
                "AUTO_MAS_ENV": "development",
                "AUTO_MAS_HTTP_PORT": "36164",
            },
        ):
            os.environ.pop("AUTO_MAS_SUPERVISED_PORT", None)
            self.assertEqual(main.resolve_http_port(True), main.DEFAULT_HTTP_PORT)

    def test_supervised_falls_back_to_default_port_on_invalid_injection(self) -> None:
        """注入值非整数或不在 1024~65535 内时回退 36163。"""

        for raw in ("abc", "80", "70000", ""):
            with self.subTest(raw=raw):
                with patch.dict(
                    os.environ,
                    {
                        "AUTO_MAS_SUPERVISED": "1",
                        "AUTO_MAS_SUPERVISED_PORT": raw,
                        "AUTO_MAS_HTTP_PORT": "40000",
                    },
                ):
                    self.assertEqual(
                        main.resolve_http_port(True), main.DEFAULT_HTTP_PORT
                    )


if __name__ == "__main__":
    unittest.main()
