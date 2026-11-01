"""统一入口的导入、缓存和对象身份回归；不运行真实桌面操作。"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


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


def test_root_packages_do_not_assemble_optional_dependencies():
    run_isolated(
        """
import sys
import app.utils, app.services, app.tools
assert not any(name.startswith((
    "app.services.common.", "app.tools.common.", "app.utils.windows.",
    "win32", "windows_toasts", "comtypes", "rapidocr", "pyautogui",
)) for name in sys.modules)
"""
    )


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_service_dispatch_and_cache(platform):
    run_isolated(
        f"""
import sys
import psutil
from importlib import import_module
from app.utils import get_logger
sys.platform = {platform!r}
import app.services as services
expected = "windows" if sys.platform == "win32" else "unsupported"
power = services.power
assert type(power).__module__ == "app.services." + expected + ".power"
assert services.__dict__["power"] is power
assert power is import_module("app.services." + expected + ".power").power
startup = services.startup
assert startup is import_module("app.services." + expected + ".startup").startup
assert startup is services.__dict__["startup"]
assert "custom_script_native" in dir(services)
try:
    services.unknown_capability
except AttributeError:
    pass
else:
    raise AssertionError("unknown capability accepted")
"""
    )


@pytest.mark.parametrize("first", ["common", "root"])
@pytest.mark.parametrize(
    ("package", "name"),
    [
        ("services", "config_center"),
        ("services", "gi_updater"),
        ("tools", "community"),
        ("tools", "game_calendar"),
    ],
)
def test_root_entry_and_shared_implementation_share_module_state(package, name, first):
    run_isolated(
        f"""
from importlib import import_module
package = import_module("app." + {package!r})
paths = {{
    "common": lambda: import_module("app." + {package!r} + ".common." + {name!r}),
    "root": lambda: getattr(package, {name!r}),
}}
first = paths[{first!r}]()
assert all(load() is first for load in paths.values())
sentinel = object()
first._state_marker = sentinel
assert all(load()._state_marker is sentinel for load in paths.values())
"""
    )


def test_engine_root_entry_keeps_classes_without_loading_host_pipeline():
    run_isolated(
        """
import sys
from app.services import gi_updater
from app.services.common import gi_updater as implementation
from app.services.common.gi_updater.games import GameUpdater
assert gi_updater is implementation
assert gi_updater.GameUpdater is GameUpdater
assert "app.services.common.gi_updater.pipeline" not in sys.modules
"""
    )


@pytest.mark.parametrize(
    ("backend", "suffix", "interpreter"),
    [
        ("common", ".py", sys.executable),
        ("windows", ".cmd", "cmd.exe"),
        ("windows", ".ps1", "powershell.exe"),
        ("common", ".ps1", "pwsh"),
        ("common", ".sh", "bash"),
        ("windows", ".sh", "bash"),
    ],
)
def test_script_commands_use_backend_and_preserve_path_arguments(
    backend, suffix, interpreter
):
    from importlib import import_module

    module_path = (
        "app.services.common.custom_script.native"
        if backend == "common"
        else "app.services.windows.custom_script_native"
    )
    module = import_module(module_path)
    path = Path("folder with spaces") / ("script" + suffix)
    command = module.build(path)
    assert command[0] == interpreter
    assert str(path) in command


def test_shared_script_backend_rejects_windows_batch():
    from app.services.common.custom_script import native as custom_script_native
    from app.utils import UnsupportedPlatformError

    with pytest.raises(UnsupportedPlatformError, match="windows_batch_script"):
        custom_script_native.build(Path("script.cmd"))
    assert custom_script_native.build(Path("readme.txt")) is None
