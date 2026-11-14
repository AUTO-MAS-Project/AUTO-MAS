import os
import unittest
from unittest.mock import patch

import main


class ResolveHttpPortTest(unittest.TestCase):
    """端口解析用例单独成文件：本模块只依赖 main，不触发 app.services 的循环导入。"""

    def test_default_port_follows_application_environment(self) -> None:
        """开发环境错开端口，用户已装正式版仍可同时运行。"""
        for development, expected in (
            (False, main.DEFAULT_HTTP_PORT),
            (True, main.DEV_HTTP_PORT),
        ):
            with self.subTest(development=development):
                with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": ""}):
                    self.assertEqual(main.resolve_http_port(development), expected)

    def test_environment_variable_overrides_both(self) -> None:
        with patch.dict(os.environ, {"AUTO_MAS_HTTP_PORT": "40000"}):
            self.assertEqual(main.resolve_http_port(True), 40000)
            self.assertEqual(main.resolve_http_port(False), 40000)

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


if __name__ == "__main__":
    unittest.main()
