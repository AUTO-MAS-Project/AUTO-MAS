"""公共能力入口：平台选择、惰性导入和公共对象身份。"""

import subprocess
import sys

import pytest


def run_isolated(code: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_script_domains_are_pure_and_models_do_not_import_runtime():
    run_isolated(
        """
import importlib.abc
import sys
import threading

sys.dont_write_bytecode = True
check_side_effects = True

class NoRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("app.task", "app.core", "app.services", "app.api")):
            raise AssertionError(f"config imported runtime: {fullname}")

def no_side_effect(event, args):
    if not check_side_effects:
        return
    if event in ("socket.connect", "subprocess.Popen", "os.mkdir", "os.remove", "os.rename"):
        raise AssertionError(f"import caused side effect: {event}")
    if event == "open" and isinstance(args[1], str) and any(flag in args[1] for flag in "wax+"):
        raise AssertionError("import wrote a file")

def no_thread(*args, **kwargs):
    if check_side_effects:
        raise AssertionError("import started a thread")
    return original_thread_start(*args, **kwargs)

sys.meta_path.insert(0, NoRuntime())
sys.addaudithook(no_side_effect)
original_thread_start = threading.Thread.start
threading.Thread.start = no_thread

from app.domain.MAA import constants as maa
from app.domain.MaaEnd import constants as maaend
from app.domain.MSS import constants as mss
from app.domain.SRC import constants as starrail
check_side_effects = False
from app.models import schema
from app.models.config import MaaUserConfig, MaaEndUserConfig, SrcUserConfig, HSRUserConfig, MSSUserConfig
assert schema.MSSPlanKey().TribulationStage == mss.MSS_DEFAULT_TRIBULATION_STAGE
"""
    )


@pytest.mark.parametrize(
    ("platform", "backend"),
    [("win32", "windows"), ("darwin", "common"), ("linux", "common")],
)
def test_notification_dispatch_is_lazy(platform, backend):
    run_isolated(
        f"""
import sys
sys.platform = {platform!r}
import app.utils as utils
assert not any(name.startswith(("win32", "windows_toasts", "plyer", "cv2", "rapidocr", "pyautogui", "app.utils.common.emulator")) for name in sys.modules)
assert utils.notification.__name__ == "app.utils.{backend}.notification"
assert "windows_toasts" not in sys.modules
assert "plyer" not in sys.modules
"""
    )


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_missing_window_capability_reports_unsupported(platform):
    run_isolated(
        f"""
import sys
sys.platform = {platform!r}
from app.utils import window, UnsupportedPlatformError
try:
    window.get_main_window_handle(1)
except UnsupportedPlatformError as error:
    assert error.capability == "window"
else:
    raise AssertionError("missing capability succeeded")
assert not any(name.startswith("app.utils.windows.") for name in sys.modules)
"""
    )


@pytest.mark.parametrize("first", ["process", "LogMonitor", "LogPatternExtractor"])
def test_public_classes_keep_identity_after_deep_import(first):
    run_isolated(
        f"""
from importlib import import_module
import_module("app.utils.common." + {first!r})
from app.utils import ProcessManager, ProcessRunner, LogMonitor, RegexMatcher
from app.utils.common.process import ProcessManager as Manager, ProcessRunner as Runner
from app.utils.common.LogMonitor import LogMonitor as Monitor
from app.utils.common.LogPatternExtractor import RegexMatcher as Matcher
assert ProcessManager is Manager
assert ProcessRunner is Runner
assert LogMonitor is Monitor
assert RegexMatcher is Matcher
assert all(isinstance(item, type) for item in (Manager, Runner, Monitor, Matcher))
"""
    )


def test_backend_errors_do_not_select_common_implementation():
    run_isolated(
        """
import sys
from types import ModuleType
import ctypes
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
from app.utils import notification
sender = notification.prepare_sender()
try:
    sender(title="标题😀", message="内容", app_name="AUTO-MAS", app_icon="", timeout=5, ticker="", toast=True)
except RuntimeError:
    pass
else:
    raise AssertionError("send failure swallowed")
assert "app.utils.common.notification" not in sys.modules
assert "plyer" not in sys.modules
"""
    )


def test_declared_native_only_capability_uses_dummy():
    run_isolated(
        """
import app.utils as utils
utils._PLATFORM_MODULES["other-platform"] = {"native_only": ".other.native_only"}
try:
    utils.native_only.execute()
except utils.UnsupportedPlatformError as error:
    assert error.capability == "native_only"
else:
    raise AssertionError("dummy did not fail")
"""
    )
