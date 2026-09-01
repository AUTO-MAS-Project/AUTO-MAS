"""运行池解释器自检：ABI 对得上不代表标准库能用。

真机现场（2026-08-31）：用户的 worker 起来后在 ``maa/library.py`` 第 1 行
``import ctypes`` 处炸掉，抛出 ctypes 内部的 ``class must define a '_type_'
attribute``。而运行池的 ``verify_python`` 明明会启动解释器做校验——它没拦住，
是因为探针只 import ``json/platform/sys/sysconfig``，而 version、soabi、
platform 这几项**全部来自解释器二进制**，标准库那一半坏了照样报得一模一样。

MaaFW 的 Python 绑定完全建立在 ctypes 上，所以把 ctypes 放进同一个探针脚本
是零额外开销的：解释器本来就要起一次。
"""

import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import app.core  # noqa: F401  # 初始化宿主配置

from app.task.MaaFW.tools.core.automas_maafw_runtime_pool import installer


class ProbeScriptTest(unittest.TestCase):
    """探针脚本本身。"""

    def test_probe_imports_ctypes(self) -> None:
        """否则标准库坏掉时探针依然全绿——真机上就是这么漏过去的。"""

        self.assertIn("import ctypes", installer._IDENTITY_PROBE_SCRIPT)

    def test_probe_still_reports_every_identity_field(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", installer._IDENTITY_PROBE_SCRIPT],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        import json

        payload = json.loads(result.stdout)
        for field in (
            "implementation",
            "cacheTag",
            "soabi",
            "version",
            "shortVersion",
            "platform",
            "architecture",
        ):
            self.assertTrue(str(payload.get(field) or "").strip(), field)


class BrokenStdlibTest(unittest.TestCase):
    """标准库不可用时要当场失败，并且说人话。"""

    def _fake_python(self, tmp: Path, body: str) -> Path:
        """造一个只会按 body 行事的假解释器（.cmd，避免依赖真 Python）。"""

        script = tmp / "fake.py"
        script.write_text(body, encoding="utf-8")
        launcher = tmp / "fake.cmd"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n', encoding="utf-8"
        )
        return launcher

    def test_ctypes_failure_is_reported_as_a_stdlib_problem(self) -> None:
        with TemporaryDirectory() as name:
            tmp = Path(name)
            fake = self._fake_python(
                tmp,
                textwrap.dedent(
                    """
                    import sys
                    sys.stderr.write(
                        'Traceback (most recent call last):\\n'
                        '  File "ctypes\\\\__init__.py", line 157, in <module>\\n'
                        "AttributeError: class must define a '_type_' attribute\\n"
                    )
                    sys.exit(1)
                    """
                ),
            )
            with self.assertRaises(RuntimeError) as caught:
                installer.probe_python_identity(fake)

        message = str(caught.exception)
        self.assertIn("标准库 ctypes 不可用", message)
        self.assertIn("不同构建", message)
        self.assertNotIn("ABI 探测失败", message, "别再报成 ABI 问题，会带偏排查")

    def test_unrelated_failure_keeps_the_generic_message(self) -> None:
        with TemporaryDirectory() as name:
            tmp = Path(name)
            fake = self._fake_python(
                tmp,
                "import sys\nsys.stderr.write('some other boom\\n')\nsys.exit(3)\n",
            )
            with self.assertRaises(RuntimeError) as caught:
                installer.probe_python_identity(fake)

        message = str(caught.exception)
        self.assertIn("ABI 探测失败", message)
        self.assertNotIn("标准库 ctypes", message)


class PythonInstallMirrorTest(unittest.TestCase):
    """解释器下载镜像。

    包索引一直有 AUTO_MAS_UV_INDEX_URL，但 uv 下载 CPython 走的是
    python-build-standalone 的 GitHub Release，此前没有任何镜像开关——受限网络
    下这一步要么超时，要么拿到不完整的解释器。
    """

    def _env(self, overrides):
        with TemporaryDirectory() as name:
            tmp = Path(name)
            with mock.patch.dict(os.environ, overrides, clear=False):
                return installer._pool_python_environment(
                    tmp / "python", tmp / "cache"
                )

    def test_mirror_is_applied_when_configured(self) -> None:
        env = self._env(
            {
                installer.AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV: "https://mirror.example/pbs",
                "UV_PYTHON_INSTALL_MIRROR": "",
            }
        )
        self.assertEqual(
            env["UV_PYTHON_INSTALL_MIRROR"], "https://mirror.example/pbs"
        )

    def test_explicit_uv_variable_wins(self) -> None:
        """显式设置的 UV_* 优先，本变量只作兜底。"""

        env = self._env(
            {
                installer.AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV: "https://ours.example",
                "UV_PYTHON_INSTALL_MIRROR": "https://theirs.example",
            }
        )
        self.assertEqual(env["UV_PYTHON_INSTALL_MIRROR"], "https://theirs.example")

    def test_absent_by_default(self) -> None:
        env = self._env(
            {
                installer.AUTO_MAS_UV_PYTHON_INSTALL_MIRROR_ENV: "",
                "UV_PYTHON_INSTALL_MIRROR": "",
            }
        )
        self.assertFalse(str(env.get("UV_PYTHON_INSTALL_MIRROR") or "").strip())

    def test_install_dir_is_still_pinned_to_the_pool(self) -> None:
        with TemporaryDirectory() as name:
            tmp = Path(name)
            env = installer._pool_python_environment(tmp / "python", tmp / "cache")
        self.assertEqual(env["UV_PYTHON_INSTALL_DIR"], str(tmp / "python"))


if __name__ == "__main__":
    unittest.main()
