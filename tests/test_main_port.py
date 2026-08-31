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


if __name__ == "__main__":
    unittest.main()
