"""公共能力入口：平台选择、惰性导入和公共对象身份。"""

import os
import subprocess
import sys


def run_isolated(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_backend_errors_do_not_select_common_implementation():
    run_isolated(
        """
import sys
from types import ModuleType
import ctypes
from app.core.notify import native as notification
sys.platform = "win32"
ctypes.WinDLL = lambda *args, **kwargs: object()
backend = ModuleType("windows_toasts")
class Toast:
    pass
class WindowsToaster:
    def __init__(self, name):
        pass
    def show_toast(self, toast):
        raise RuntimeError("send failed")
backend.Toast = Toast
backend.WindowsToaster = WindowsToaster
sys.modules["windows_toasts"] = backend
sender = notification.prepare_sender()
try:
    sender(title="标题😀", message="内容", app_name="AUTO-MAS", app_icon="", timeout=5, ticker="", toast=True)
except RuntimeError:
    pass
else:
    raise AssertionError("send failure swallowed")
assert "app.core.notify.native.common" not in sys.modules
assert "plyer" not in sys.modules
"""
    )
