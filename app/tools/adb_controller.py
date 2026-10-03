"""ADB 控制器的模拟器增强配置，供运行任务与诊断截图共用。"""

import importlib.util
import os
from pathlib import Path
from typing import Any


def same_adb_device(left: str, right: str) -> bool:
    """抹平本机模拟器的控制台端口与 ADB 端口、localhost 写法差异。"""

    def normalize(address: str) -> str:
        address = address.strip().lower()
        console_port = address.removeprefix("emulator-")
        if console_port != address and console_port.isdigit():
            return f"127.0.0.1:{int(console_port) + 1}"
        if address.startswith("localhost:"):
            return "127.0.0.1:" + address.removeprefix("localhost:")
        return address

    return normalize(left) == normalize(right)


def build_ldplayer_extra_config(
    *, manager_path: Path, native_index: int, pid: int = 0
) -> dict[str, Any]:
    """按真实安装与原生实例号构造雷电截图增强配置。"""

    root = manager_path.parent
    config: dict[str, Any] = {
        "enable": True,
        "index": native_index,
        "path": root.as_posix(),
        "pid": pid,
    }
    library = root / "ldopengl64.dll"
    if library.exists():
        config["lib"] = library.as_posix()
    return {"extras": {"ld": config}}


def build_mumu_extra_config(*, manager_path: Path, native_index: int) -> dict[str, Any]:
    """按真实安装与原生实例号构造 MuMu 截图、输入增强配置。"""

    root = manager_path.parent.parent
    config: dict[str, Any] = {
        "enable": True,
        "index": native_index,
        "path": root.as_posix(),
    }
    for library in (
        root / "nx_main" / "sdk" / "external_renderer_ipc.dll",
        root / "shell" / "sdk" / "external_renderer_ipc.dll",
    ):
        if library.exists():
            config["lib"] = library.as_posix()
            break
    return {"extras": {"mumu": config}}


# EmulatorExtras (ADB 截图/输入加速) 是 MaaFW 的 Windows-only 特性。每个模拟器
# 族支持的加速子集是固定的，此关系表对齐 MaaFW 控制器定义。能力是否真正可用取
# 决于运行时安装的 maa 是否带 MaaAdbControlUnit.dll，由下方探测函数按真实环境判断。
_EMULATOR_EXTRA_RELATION: dict[str, dict[str, bool]] = {
    "mumu": {"screencap": True, "input": True},
    "ldplayer": {"screencap": True, "input": False},
}


def _maafw_emulator_extras_runtime_available() -> bool:
    """Return whether the installed MaaFW runtime exposes ADB EmulatorExtras.

    定位运行环境真实安装的 ``maa`` 包并检查 ``MaaAdbControlUnit.dll`` 是否存在。
    用 ``importlib.util.find_spec`` 定位包目录——它只查找 spec、不执行 ``maa/__init__``
    也不加载原生绑定，因此**本函数自身**不触发 maa 导入。非 Windows 不可用。

    注意不要据此推断「maa 未被载入主进程」：``app/core/maa_manager.py`` 在模块级
    ``from maa.tasker import Tasker`` 并在导入时实例化单例，而 ``app.core`` 是全应用
    公共入口，进程里实际早已完成原生初始化。那是上游基线既有的第二层原生集成，
    与本层无关，也不要顺手去改它。

    """

    if os.name != "nt":
        return False
    spec = importlib.util.find_spec("maa")
    if spec is None or not spec.submodule_search_locations:
        return False
    maa_package_dir = Path(next(iter(spec.submodule_search_locations)))
    return (maa_package_dir / "bin" / "MaaAdbControlUnit.dll").is_file()


def build_adb_emulator_extra_capabilities() -> dict[str, dict[str, bool]]:
    """Return per-emulator EmulatorExtras capabilities for the installed MaaFW."""

    if not _maafw_emulator_extras_runtime_available():
        return {}
    return {
        emulator_type: dict(relation)
        for emulator_type, relation in _EMULATOR_EXTRA_RELATION.items()
    }
