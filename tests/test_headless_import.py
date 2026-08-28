import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# 在干净解释器中屏蔽桌面依赖，模拟无 DISPLAY 的 Linux 会话
_PROBE = textwrap.dedent(
    """
    import sys


    class _BlockDesktopDeps:
        BLOCKED = {"pyautogui", "mouseinfo", "pyscreeze", "Xlib"}

        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in self.BLOCKED:
                raise ImportError(f"无图形会话不可用: {name}")
            return None


    sys.meta_path.insert(0, _BlockDesktopDeps())

    from app.core import Config, MainTimer, TaskManager  # noqa: F401

    assert "pyautogui" not in sys.modules, "启动链不应加载 pyautogui"
    print("OK")
    """
)


class HeadlessImportTest(unittest.TestCase):
    """后端启动链不得依赖桌面图形环境。

    无图形会话的 Linux 缺少 DISPLAY 时 pyautogui 导入即失败，
    该依赖必须留在 Windows 专属路径内。
    """

    def test_core_imports_without_desktop_dependencies(self) -> None:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"无图形环境下导入后端启动链失败:\n{result.stderr}",
        )
        self.assertIn("OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
