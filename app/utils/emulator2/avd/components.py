#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""魔改 AVD 根目录：路径、元数据（``mas-avd.json``）与组件检查。

组件全部随模拟器内测包提供（模拟器、平台工具、系统镜像，可选的轻量桌面），MAS **不下载任何组件**。
这里只检查根目录里它们在不在：关键文件、模拟器是不是我们的自编版、内测包编号够不够新。
缺了就明确说缺哪一项，让用户换完整的内测包。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.utils import get_logger

from .constants import (
    ADB_NO_LOCAL_SCAN_ENV,
    ADB_SERVER_PORT,
    AVD_DIR,
    COMPONENTS_DIR,
    EMULATOR_COMPONENT_ID,
    EMULATOR_COMPONENT_NAME,
    FOSSIFY_LAUNCHER,
    MAX_NATIVE_INDEX,
    METADATA_FILE,
    MIN_MOD_AVD_BUILD,
    MOD_AVD_BUILD_PREFIX,
    REQUIRED_COMPONENTS,
    SCRIPT_ADB_SERVER_PORT,
    SDK_DIR,
    Component,
    console_port,
    valid_native_index,
)

logger = get_logger("魔改 AVD 组件")

#: 每个组件必须存在的文件——只看目录在不在不够，解压到一半的目录也是「在」的。
_KEY_FILES = {
    "platform-tools": ("adb.exe",),
    "emulator": ("emulator.exe", "qemu/windows-x86_64/qemu-system-x86_64.exe"),
    "system-image": ("system.img", "vendor.img", "kernel-ranchu", "ramdisk.img"),
}

#: 组件不全时给用户的建议（MAS 不下载组件）。
FULL_PACKAGE_ADVICE = "请使用完整的模拟器内测包"


# ---- 根目录与元数据 --------------------------------------------------------


def root_key(root: str | Path) -> str:
    """根目录的规范化键，按它去重。"""
    return os.path.normcase(os.path.abspath(str(root)))


def sdk_dir(root: str | Path) -> Path:
    """内测包里的 SDK：``<根>\\sdk``。实际运行用哪个 SDK 见 :func:`runtime_sdk_dir`。"""
    return Path(root) / SDK_DIR


def local_sdk_root(root: str | Path) -> Path | None:
    """``mas-avd.json`` 的 ``sdkRoot``：指定的本地 SDK 根目录（开发阶段指向自编模拟器）。

    设了它，模拟器、adb、系统镜像都从这里取，``<根>\\sdk`` 不再用；不建链接。没设返回 ``None``。
    """
    raw = read_metadata(root).get("sdkRoot")
    if isinstance(raw, str) and raw.strip():
        return Path(raw.strip())
    return None


def runtime_sdk_dir(root: str | Path) -> Path:
    """实际运行用的 SDK 根：指定了本地 SDK 就用它，否则是 ``<根>\\sdk``。"""
    return local_sdk_root(root) or sdk_dir(root)


def manager_key_exe(root: str | Path) -> Path:
    """这条安装的「主管理器程序」路径：``<根>\\sdk\\emulator\\emulator.exe``。

    它是 ``DeviceRef.manager_path`` 与实例锁的键，靠它反推根目录
    （:func:`root_from_manager_exe`），所以始终落在根目录下，不随 ``sdkRoot`` 变；
    指定了本地 SDK 时这个文件可以不存在，真正启动的程序见 :func:`emulator_exe`。
    """
    return sdk_dir(root) / "emulator" / "emulator.exe"


def emulator_exe(root: str | Path) -> Path:
    return runtime_sdk_dir(root) / "emulator" / "emulator.exe"


def adb_exe(root: str | Path) -> Path:
    return runtime_sdk_dir(root) / "platform-tools" / "adb.exe"


def adb_server_port(root: str | Path) -> int:
    """私有 adb server 的端口：``mas-avd.json`` 的 ``adbServerPort``，没设用 20050。

    不收 5037（生产在用），也不收任何一台实例的控制台 / adb / gRPC 端口；不合规时回到 20050。
    """
    port = _metadata_port(root, "adbServerPort")
    return port if port is not None else ADB_SERVER_PORT


def script_adb_server_port(root: str | Path) -> int:
    """脚本（MaaFW 的 worker / agent）在魔改 AVD 实例上用的 adb server 端口。

    ``mas-avd.json`` 的 ``scriptAdbServerPort``，默认 20049。脚本用 SDK 的新版 adb，跑在 5037 上会和
    雷电 / MuMu 自带的旧版 adb 互杀 server、掉线（用户定：单独一个端口）。校验同 ``adbServerPort``，
    另外不能和私有 server 同一个端口；不合规时回到默认值。
    """
    private = adb_server_port(root)
    port = _metadata_port(root, "scriptAdbServerPort")
    if port is not None and port != private:
        return port
    return SCRIPT_ADB_SERVER_PORT if SCRIPT_ADB_SERVER_PORT != private else 20048


def script_adb_env(root: str | Path) -> dict[str, str]:
    """脚本进程要叠加的环境变量：把它的 adb 指到 :func:`script_adb_server_port`；脚本的 adb 万一
    自己拉起这个 server，也不让它去扫 5555–5585 连上同机的雷电（:data:`~.constants.ADB_NO_LOCAL_SCAN_ENV`）。"""
    return {
        "ANDROID_ADB_SERVER_PORT": str(script_adb_server_port(root)),
        **ADB_NO_LOCAL_SCAN_ENV,
    }


def _metadata_port(root: str | Path, key: str) -> int | None:
    """``mas-avd.json`` 里的端口：不收 5037（生产在用），也不收任何实例的控制台 / adb / gRPC 端口。"""
    raw = read_metadata(root).get(key)
    try:
        port = int(raw)
    except (TypeError, ValueError):
        return None
    if not 1024 <= port <= 65535 or port == 5037 or port in _instance_ports():
        return None
    return port


def _instance_ports() -> frozenset[int]:
    ports = set()
    for index in range(MAX_NATIVE_INDEX + 1):
        if valid_native_index(index):
            console = console_port(index)
            ports.update((console, console + 1, console + 2))
    return frozenset(ports)


def avd_home(root: str | Path) -> Path:
    return Path(root) / AVD_DIR


def launcher_apk(root: str | Path) -> Path:
    return Path(root) / COMPONENTS_DIR / FOSSIFY_LAUNCHER.file_name


def root_from_manager_exe(manager_exe: str | Path) -> Path:
    """``<根>\\sdk\\emulator\\emulator.exe`` → ``<根>``。"""
    return Path(manager_exe).resolve().parents[2]


def read_metadata(root: str | Path) -> dict[str, Any]:
    """读 ``mas-avd.json``。不存在或读不出按空字典处理。"""
    path = Path(root) / METADATA_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_metadata(root: str | Path, data: dict[str, Any]) -> None:
    """原子写 ``mas-avd.json``：先写临时文件再替换，写到一半断电也不留半个 JSON。"""
    path = Path(root) / METADATA_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def update_metadata(root: str | Path, **changes: Any) -> dict[str, Any]:
    data = read_metadata(root)
    data.update(changes)
    write_metadata(root, data)
    return data


def ensure_metadata(root: str | Path) -> bool:
    """根目录里还没有 ``mas-avd.json``（内测包刚解压出来）时补一份：记下当时装着的各组件版本和添加
    时间。已有的不动。返回是否新写了。"""
    if (Path(root) / METADATA_FILE).exists():
        return False
    status = install_status(root)
    write_metadata(
        root,
        {
            "components": {
                item["id"]: item["version"] or ""
                for item in status["components"]
                if item["installed"]
            },
            "addedAt": datetime.now().isoformat(timespec="seconds"),
        },
    )
    return True


def _read_properties(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    result: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


# ---- 组件检查 --------------------------------------------------------------


def component_installed(root: str | Path, component: Component) -> bool:
    """组件的关键文件是不是都在（实际运行用的 SDK 里）。"""
    target = runtime_sdk_dir(root) / component.target
    return all((target / name).is_file() for name in _KEY_FILES[component.id])


def installed_revision(root: str | Path, component: Component) -> str | None:
    """实际运行用的 SDK 里这个组件的 ``source.properties`` 版本号；读不到返回 ``None``。"""
    props = _read_properties(
        runtime_sdk_dir(root) / component.target / "source.properties"
    )
    return props.get("Pkg.Revision") or None


def launcher_present(root: str | Path) -> bool:
    """内测包里带的轻量桌面安装包在不在（大小对得上才算）。"""
    path = launcher_apk(root)
    try:
        return path.stat().st_size == FOSSIFY_LAUNCHER.size
    except OSError:
        return False


def read_emulator_version(root: str | Path) -> str | None:
    """``sdk\\emulator\\source.properties`` 的 ``Pkg.Revision``。没有返回 ``None``。"""
    props = _read_properties(runtime_sdk_dir(root) / "emulator" / "source.properties")
    return props.get("Pkg.Revision") or None


# ---- Android 模拟器：只认自编版 -------------------------------------------------

#: 自编版的标志：qemu 里有 ``virtio-balloon-pci`` 的 ``free-page-reporting`` 属性（sdk-mas19 起才有；
#: 谷歌原版 37.1.11 与更早的自编版 sdk-mas18 都没有，10-04 核实）。qemu 没有可靠的查询开关，直接在
#: exe 的字节里找属性名。
_SELF_BUILT_MARK = b"free-page-reporting"
_SELF_BUILT_CHUNK = 4 * 1024 * 1024
#: ``(路径, 修改时间, 大小)`` → 是否自编版。换了模拟器二进制修改时间就变，自然重查。
_self_built_cache: dict[tuple[str, int, int], bool] = {}


def qemu_headless_exe(root: str | Path) -> Path:
    return (
        runtime_sdk_dir(root)
        / "emulator"
        / "qemu"
        / "windows-x86_64"
        / "qemu-system-x86_64-headless.exe"
    )


def qemu_has_self_built_mark(exe: str | Path) -> bool:
    """这个 qemu 是不是我们的自编版（找 :data:`_SELF_BUILT_MARK`）。exe 不存在、读不了都算不是。"""
    path = Path(exe)
    try:
        stat = path.stat()
    except OSError:
        return False
    key = (os.path.normcase(str(path)), stat.st_mtime_ns, stat.st_size)
    cached = _self_built_cache.get(key)
    if cached is not None:
        return cached
    mark = _SELF_BUILT_MARK
    found = False
    tail = b""
    try:
        with path.open("rb") as file:
            while True:
                chunk = file.read(_SELF_BUILT_CHUNK)
                if not chunk:
                    break
                if mark in tail + chunk:
                    found = True
                    break
                tail = chunk[-(len(mark) - 1) :]
    except OSError as e:
        logger.warning(f"读取 {path} 判断模拟器版本失败，按不是内测包处理: {e}")
        return False
    _self_built_cache[key] = found
    return found


def emulator_present(root: str | Path) -> bool:
    """实际运行用的 SDK 里模拟器的关键文件都在（不管是不是自编版）。"""
    target = runtime_sdk_dir(root) / "emulator"
    return all((target / name).is_file() for name in _KEY_FILES[EMULATOR_COMPONENT_ID])


def emulator_self_built(root: str | Path) -> bool:
    """根目录里的模拟器是我们的自编版（魔改 AVD 内测包里的那份）。只有它才能用。"""
    return emulator_present(root) and qemu_has_self_built_mark(qemu_headless_exe(root))


_MOD_BUILD_ID = re.compile(rf"{re.escape(MOD_AVD_BUILD_PREFIX)}(\d+)")


def read_mod_build(root: str | Path) -> int | None:
    """内测包编号：``sdk\\emulator\\source.properties`` 的 ``Pkg.BuildId=mas-<编号>``。

    谷歌原版那里是一串纯数字的构建号，不算；没有这一行、写法不对都返回 ``None``。"""
    props = _read_properties(runtime_sdk_dir(root) / "emulator" / "source.properties")
    match = _MOD_BUILD_ID.fullmatch((props.get("Pkg.BuildId") or "").strip())
    return int(match.group(1)) if match else None


def mod_build_label(build: int | None) -> str | None:
    """``19`` → ``mas-19``；读不到编号返回 ``None``。"""
    return None if build is None else f"{MOD_AVD_BUILD_PREFIX}{build}"


def emulator_build_ok(root: str | Path) -> bool:
    """内测包编号读得到、且不低于 :data:`~.constants.MIN_MOD_AVD_BUILD`。"""
    build = read_mod_build(root)
    return build is not None and build >= MIN_MOD_AVD_BUILD


def emulator_ready(root: str | Path) -> bool:
    """模拟器能用：是自编版（能力探测）**并且**内测包编号够新，两项都要满足。"""
    return emulator_self_built(root) and emulator_build_ok(root)


def _emulator_item(root: Path, local: bool) -> dict[str, Any]:
    """组件清单里的「Android 模拟器」一项：根目录里有没有够新的内测包自编版。"""
    self_built = emulator_self_built(root)
    ready = self_built and emulator_build_ok(root)
    return {
        "id": EMULATOR_COMPONENT_ID,
        "name": EMULATOR_COMPONENT_NAME,
        "version": (read_emulator_version(root) or "")
        if emulator_present(root)
        else "",
        # 只有自编版才报编号；谷歌原版的构建号不是内测包编号
        "build": mod_build_label(read_mod_build(root)) if self_built else None,
        "outdatedTestPackage": self_built and not ready,
        "installed": ready,
        "optional": False,
        "localSdk": local,
        "testPackage": ready,
        "needsTestPackage": not ready,
    }


def install_status(root: str | Path) -> dict[str, Any]:
    """根目录里组件的现状。只读，不联网。``missing`` 是缺着的必需组件名（含不合格的模拟器）。"""
    root = Path(root)
    local = local_sdk_root(root) is not None
    items: list[dict[str, Any]] = []
    for component in REQUIRED_COMPONENTS:
        installed = component_installed(root, component)
        items.append(
            {
                "id": component.id,
                "name": component.name,
                "version": installed_revision(root, component) or ""
                if installed
                else "",
                "build": None,
                "outdatedTestPackage": False,
                "installed": installed,
                "optional": False,
                "localSdk": local,
                "testPackage": False,
                "needsTestPackage": False,
            }
        )
    items.insert(1, _emulator_item(root, local))
    items.append(
        {
            "id": FOSSIFY_LAUNCHER.id,
            "name": FOSSIFY_LAUNCHER.name,
            "version": FOSSIFY_LAUNCHER.version,
            "build": None,
            "outdatedTestPackage": False,
            "installed": launcher_present(root),
            "optional": True,
            "localSdk": False,
            "testPackage": False,
            "needsTestPackage": False,
        }
    )
    missing = [
        item["name"] for item in items if not item["optional"] and not item["installed"]
    ]
    return {
        "root": str(root),
        "ready": not missing,
        "components": items,
        "missing": missing,
    }


def missing_components_message(missing: list[str]) -> str:
    """缺组件时给用户的一句话：缺哪几项 + 用完整的内测包。"""
    return f"这个目录里缺少：{'、'.join(missing)}。{FULL_PACKAGE_ADVICE}"


__all__ = [
    "FULL_PACKAGE_ADVICE",
    "adb_exe",
    "adb_server_port",
    "avd_home",
    "component_installed",
    "emulator_build_ok",
    "emulator_exe",
    "emulator_present",
    "emulator_ready",
    "emulator_self_built",
    "ensure_metadata",
    "install_status",
    "launcher_apk",
    "launcher_present",
    "local_sdk_root",
    "manager_key_exe",
    "missing_components_message",
    "mod_build_label",
    "read_emulator_version",
    "read_metadata",
    "read_mod_build",
    "root_from_manager_exe",
    "root_key",
    "runtime_sdk_dir",
    "script_adb_env",
    "script_adb_server_port",
    "sdk_dir",
    "update_metadata",
    "write_metadata",
]
