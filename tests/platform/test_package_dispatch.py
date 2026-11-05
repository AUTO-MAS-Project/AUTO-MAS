"""统一入口的导入、缓存和对象身份回归；不运行真实桌面操作。"""

import sys
from pathlib import Path

import pytest


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
