# SPDX-License-Identifier: LGPL-3.0-only
# Copyright (c) 2025
# Adapted from MaaFramework C++ sources by the MaaFramework community.
#
# File: adb_device_finder.py
#
# Purpose:
#   Python reimplementation of MaaFramework Toolkit AdbDeviceFinder:
#   - Find running Android emulators by process keyword
#   - Resolve per-emulator ADB executable path from process location
#   - List available ADB devices/serials and verify connectivity
#   - Apply device-specific runtime config (e.g., Waydroid, MuMu, LD)
#
# Upstream references (logic and constants mapped from these files):
#   1) source/MaaToolkit/AdbDevice/AdbDeviceFinder.h
#      - Types: EmulatorConstantData, Emulator
#      - API: find(), find_specified(), find_emulators(), get_adb_path(), etc.
#   2) source/MaaToolkit/AdbDevice/AdbDeviceFinder.cpp
#      - Core logic: scanning processes, dedup serials, ADB connectivity check,
#        Waydroid detection via getprop.
#   3) source/MaaToolkit/AdbDevice/AdbDeviceWin32Finder.cpp
#      - Windows-specific emulator constant data (keywords, adb candidate paths, common serials).
#      - Special handling:
#          * LDPlayer: serials via adb devices
#          * MuMuPlayer12 / MuMuPlayer12 v5: MuMuManager.exe JSON -> host:port serials,
#            extras config structure, and method flag overrides
#   4) source/MaaToolkit/AdbDevice/AdbDeviceMacOSFinder.cpp
#      - macOS-specific emulator constant data (keywords, adb candidate paths, common serials).
#   5) include/MaaFramework/MaaDef.h
#      - Exact bitmask constants used here:
#          * MaaAdbScreencapMethod_* (EncodeToFileAndPull, Encode, RawWithGzip,
#            RawByNetcat, MinicapDirect, MinicapStream, EmulatorExtras, None, All, Default)
#          * MaaAdbInputMethod_* (AdbShell, MinitouchAndAdbKey, Maatouch,
#            EmulatorExtras, None, All, Default)
#      - The Python constants mirror these definitions 1:1.
#   6) include/Utils/Platform.h
#      - ProcessInfo shape (pid + name), list_processes/get_process_path semantics.
#
# Notes about parity vs. C++:
#   - ADB interactions:
#       In C++: via ControlUnit (LibraryHolder/ControlUnit.h + ControlUnitAPI.h)
#       In Python: use 'adb' CLI directly with subprocess for devices/connect/shell.
#   - Process enumeration / executable path:
#       In C++: Utils/Platform.{h,cpp}
#       In Python: psutil to replicate list_processes() / get_process_path().
#   - MuMu special handling:
#       In C++: run MuMuManager.exe and parse JSON; derive serials and extras.
#       In Python: same behavior implemented with subprocess + json parsing.
#   - Waydroid detection:
#       In C++: shell("getprop | grep ro.product.brand") contains "waydroid".
#       In Python: identical probe via 'adb -s ... shell'.
#
# External dependencies:
#   - psutil (process enumeration & exe path)
#   - ADB must be available (either emulator-bundled ADB resolved from process path,
#     or a system 'adb' in PATH); Python falls back to system adb if found.
#
# Platform coverage:
#   - Windows: BlueStacks / LDPlayer / Nox / MuMu (6, 12, 12 v5) / MEmu / AVD
#   - macOS: Nox / MuMuPlayerPro / AVD / Genymotion / BlueStacks
#   (All emulator keyword matches and candidate ADB paths are taken from the C++ sources above.)
#
# Limitations:
#   - This module does not load MaaFramework native ControlUnit libraries;
#     it uses adb CLI as a portable substitute. Behavior and performance may differ.
#   - Error handling is best-effort and may be less granular than C++ logging.
#
# Usage:
#   - Install dependency: pip install psutil
#   - Run directly (will auto-detect platform and emulators):
#       python adb_device_finder.py
#   - Or import AdbDeviceFinder and call find()/find_specified(adb_path)
#
# License:
#   - This file is distributed under the same license as MaaFramework: LGPL-3.0-only.
#     See the repository’s LICENSE.md for details.

"""
AdbDeviceFinder - 从 MaaFramework C++ 源码转换的 Python 实现。

该模块提供了在不同平台（Windows、macOS、Linux）上自动发现和配置 ADB 设备
（Android 模拟器）的功能。

功能：
- 通过进程扫描自动检测流行模拟器
- 解析模拟器特定的 ADB 路径
- 设备序列号枚举和连接性验证
- 模拟器特定配置（Waydroid、MuMu、LDPlayer）
- 与 MaaFramework/MaaDef.h 匹配的位掩码常量

依赖：
    - psutil: 用于进程枚举和路径解析
"""

from __future__ import annotations

import json
import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------- 日志记录 ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------- 来自 MaaFramework/MaaDef.h 的常量 ----------
class ScreencapMethod(IntFlag):
    """ADB 截屏方法 (uint64 位掩码)。"""

    NONE = 0
    ENCODE_TO_FILE_AND_PULL = 1 << 0
    ENCODE = 1 << 1
    RAW_WITH_GZIP = 1 << 2
    RAW_BY_NETCAT = 1 << 3
    MINICAP_DIRECT = 1 << 4
    MINICAP_STREAM = 1 << 5
    EMULATOR_EXTRAS = 1 << 6

    @classmethod
    def all(cls) -> int:
        """获取所有截屏方法。"""
        return (1 << 64) - 1

    @classmethod
    def default(cls) -> int:
        """获取默认截屏方法（排除有问题的方法）。"""
        return (
            cls.all() & ~cls.RAW_BY_NETCAT & ~cls.MINICAP_DIRECT & ~cls.MINICAP_STREAM
        )


class InputMethod(IntFlag):
    """ADB 输入方法 (uint64 位掩码)。"""

    NONE = 0
    ADB_SHELL = 1 << 0
    MINITOUCH_AND_ADB_KEY = 1 << 1
    MAATOUCH = 1 << 2
    EMULATOR_EXTRAS = 1 << 3

    @classmethod
    def all(cls) -> int:
        """获取所有输入方法。"""
        return (1 << 64) - 1

    @classmethod
    def default(cls) -> int:
        """获取默认输入方法（排除模拟器额外功能）。"""
        return cls.all() & ~cls.EMULATOR_EXTRAS


# ---------- 数据结构 ----------
@dataclass
class ProcessInfo:
    """关于正在运行的进程的信息。"""

    pid: int = 0
    name: str = ""

    def __str__(self) -> str:
        return f"{self.pid} {self.name}"


@dataclass
class EmulatorConstantData:
    """
    模拟器类型的常量配置数据。

    属性：
        keyword: 用于识别模拟器的进程名称子字符串。
        adb_candidate_paths: 从进程目录到 ADB 可执行文件的相对路径。
        adb_common_serials: 此模拟器的常见 ADB 序列地址。
    """

    keyword: str
    adb_candidate_paths: List[Path] = field(default_factory=list)
    adb_common_serials: List[str] = field(default_factory=list)


@dataclass
class Emulator:
    """
    表示检测到的正在运行的模拟器实例。

    属性：
        name: 模拟器类型名称（例如，"MuMuPlayer12"，"LDPlayer"）。
        process: 正在运行的模拟器的进程信息。
        const_data: 此模拟器类型的配置常量。
    """

    name: str
    process: ProcessInfo
    const_data: EmulatorConstantData

    def __str__(self) -> str:
        return f"name={self.name}, process={self.process}"


@dataclass
class AdbDevice:
    """
    表示已配置的 ADB 设备，准备连接。

    属性：
        name: 设备/模拟器名称。
        adb_path: ADB 可执行文件的路径。
        serial: ADB 序列字符串（例如，"127.0.0.1:5555"）。
        screencap_methods: 支持的截图方法的位掩码。
        input_methods: 支持的输入方法的位掩码。
        config: 其他设备特定配置（例如，模拟器额外功能）。
    """

    name: str = ""
    adb_path: Path = field(default_factory=Path)
    serial: str = ""
    screencap_methods: int = int(ScreencapMethod.NONE)
    input_methods: int = int(InputMethod.NONE)
    config: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"name={self.name}, adb_path={self.adb_path}, serial={self.serial}, "
            f"screencap_methods={self.screencap_methods}, input_methods={self.input_methods}, "
            f"config={self.config}"
        )


# ---------- 模拟器配置 ----------
class EmulatorConfig:
    """不同平台的模拟器配置注册表。"""

    WINDOWS: Dict[str, EmulatorConstantData] = {}
    MACOS: Dict[str, EmulatorConstantData] = {}
    LINUX: Dict[str, EmulatorConstantData] = {}

    @classmethod
    def _init_windows(cls) -> None:
        """初始化 Windows 模拟器配置。"""
        cls.WINDOWS = {
            "BlueStacks": EmulatorConstantData(
                keyword="HD-Player",
                adb_candidate_paths=[
                    Path("HD-Adb.exe"),
                    Path("Engine/ProgramFiles/HD-Adb.exe"),
                ],
                adb_common_serials=[
                    "127.0.0.1:5555",
                    "127.0.0.1:5556",
                    "127.0.0.1:5565",
                    "127.0.0.1:5575",
                ],
            ),
            "LDPlayer": EmulatorConstantData(
                keyword="dnplayer",
                adb_candidate_paths=[Path("adb.exe")],
                adb_common_serials=[],
            ),
            "Nox": EmulatorConstantData(
                keyword="Nox",
                adb_candidate_paths=[Path("nox_adb.exe")],
                adb_common_serials=["127.0.0.1:62001", "127.0.0.1:59865"],
            ),
            "MuMuPlayer6": EmulatorConstantData(
                keyword="NemuPlayer",
                adb_candidate_paths=[
                    Path("vmonitor/bin/adb_server.exe"),
                    Path("MuMu/emulator/nemu/vmonitor/bin/adb_server.exe"),
                    Path("adb.exe"),
                ],
                adb_common_serials=["127.0.0.1:7555"],
            ),
            "MuMuPlayer12": EmulatorConstantData(
                keyword="MuMuPlayer.exe",
                adb_candidate_paths=[
                    Path("vmonitor/bin/adb_server.exe"),
                    Path("MuMu/emulator/nemu/vmonitor/bin/adb_server.exe"),
                    Path("adb.exe"),
                ],
                adb_common_serials=[],
            ),
            "MuMuPlayer12 v5": EmulatorConstantData(
                keyword="MuMuNxDevice.exe",
                adb_candidate_paths=[Path("../../../nx_main/adb.exe"), Path("adb.exe")],
                adb_common_serials=[],
            ),
            "MEmuPlayer": EmulatorConstantData(
                keyword="MEmu",
                adb_candidate_paths=[Path("adb.exe")],
                adb_common_serials=["127.0.0.1:21503"],
            ),
            "AVD": EmulatorConstantData(
                keyword="qemu-system",
                adb_candidate_paths=[Path("../../../platform-tools/adb.exe")],
                adb_common_serials=["emulator-5554", "127.0.0.1:5555"],
            ),
        }

    @classmethod
    def _init_macos(cls) -> None:
        """初始化 macOS 模拟器配置。"""
        cls.MACOS = {
            "Nox": EmulatorConstantData(
                keyword="Nox",
                adb_candidate_paths=[Path("adb")],
                adb_common_serials=["127.0.0.1:62001", "127.0.0.1:59865"],
            ),
            "MuMuPlayerPro": EmulatorConstantData(
                keyword="MuMuEmulator",
                adb_candidate_paths=[Path("tools/adb")],
                adb_common_serials=["127.0.0.1:16384", "127.0.0.1:16416"],
            ),
            "AVD": EmulatorConstantData(
                keyword="qemu-system",
                adb_candidate_paths=[Path("../../../platform-tools/adb")],
                adb_common_serials=["emulator-5554", "127.0.0.1:5555"],
            ),
            "Genymotion": EmulatorConstantData(
                keyword="genymotion",
                adb_candidate_paths=[Path("player.app/Contents/MacOS/tools/adb")],
                adb_common_serials=["127.0.0.1:6555"],
            ),
            "BlueStacks": EmulatorConstantData(
                keyword="BlueStacks",
                adb_candidate_paths=[
                    Path("hd-adb"),
                    Path("BlueStacks.app/Contents/MacOS/hd-adb"),
                ],
                adb_common_serials=[
                    "127.0.0.1:5555",
                    "127.0.0.1:5556",
                    "127.0.0.1:5565",
                    "127.0.0.1:5575",
                ],
            ),
        }

    @classmethod
    def _init_linux(cls) -> None:
        """初始化 Linux 模拟器配置。"""
        cls.LINUX = {
            "AVD": EmulatorConstantData(
                keyword="qemu-system",
                adb_candidate_paths=[Path("../../../platform-tools/adb")],
                adb_common_serials=["emulator-5554", "127.0.0.1:5555"],
            ),
            "Genymotion": EmulatorConstantData(
                keyword="genymotion",
                adb_candidate_paths=[Path("tools/adb")],
                adb_common_serials=["127.0.0.1:6555"],
            ),
        }

    @classmethod
    def get_platform_config(cls) -> Dict[str, EmulatorConstantData]:
        """
        获取当前平台的模拟器配置。

        返回：
            将模拟器名称映射到其配置数据的字典。
        """
        system = platform.system()

        if system == "Windows":
            if not cls.WINDOWS:
                cls._init_windows()
            return cls.WINDOWS
        elif system == "Darwin":
            if not cls.MACOS:
                cls._init_macos()
            return cls.MACOS
        else:  # Linux 和其他系统
            if not cls.LINUX:
                cls._init_linux()
            return cls.LINUX


# ---------- ADB 控制单元 ----------
class AdbControlUnit:
    """
    用于设备发现和通信的低级 ADB 命令封装。

    该类提供了执行 ADB 命令以列出设备、建立连接和运行 shell 命令的方法。
    """

    def __init__(self, adb_path: str, serial: str) -> None:
        """
        初始化 ADB 控制单元。

        参数：
            adb_path: ADB 可执行文件的路径。
            serial: 设备序列字符串（可以为空以列出设备）。
        """
        self.adb_path = adb_path
        self.serial = serial

    def find_device(self) -> List[str]:
        """
        执行 'adb devices' 以列出所有连接的设备。

        返回：
            状态为：device, offline, unauthorized 的设备序列字符串列表。
        """
        try:
            result = subprocess.run(
                [self.adb_path, "devices"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode != 0:
                logger.error(f"adb devices 失败: {result.stderr}")
                return []

            devices: List[str] = []
            lines = [line.strip() for line in result.stdout.splitlines()]

            for line in lines[1:]:  # 跳过 "List of devices attached" 标题
                if not line or "\t" not in line:
                    continue
                serial, status = line.split("\t", 1)
                if status.strip() in ("device", "offline", "unauthorized"):
                    devices.append(serial)

            return devices
        except Exception as e:
            logger.error(f"find_device 中的异常: {e}")
            return []

    def connect(self) -> bool:
        """
        建立与设备的连接并验证 shell 访问。

        对于网络地址 (host:port)，首先执行 'adb connect'。
        然后通过简单的 shell echo 命令验证连接性。

        返回：
            如果连接成功且 shell 可访问则返回 True，否则返回 False。
        """
        try:
            # 对于网络地址，确保连接
            if ":" in self.serial and not self.serial.startswith("emulator-"):
                result = subprocess.run(
                    [self.adb_path, "connect", self.serial],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if result.returncode != 0:
                    logger.warning(
                        f"adb connect {self.serial} 失败: {result.stderr or result.stdout}"
                    )

            # 验证 shell 访问
            result = subprocess.run(
                [self.adb_path, "-s", self.serial, "shell", "echo", "ok"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"connect 异常: {e}")
            return False

    def shell(self, command: str) -> Tuple[bool, str]:
        """
        在设备上执行 shell 命令。

        参数：
            command: 要执行的 shell 命令。

        返回：
            (success: bool, output: str) 的元组。
        """
        try:
            result = subprocess.run(
                [self.adb_path, "-s", self.serial, "shell", command],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            logger.debug(f"shell 异常: {e}")
            return False, ""


# ---------- 主查找器类 ----------
class AdbDeviceFinder:
    """
    跨模拟器发现和配置 ADB 设备的主类。

    该类扫描正在运行的进程以检测模拟器，解析其 ADB 路径，
    枚举设备序列号，并应用模拟器特定的配置。
    """

    def __init__(self) -> None:
        """初始化 ADB 设备查找器，配置为空。"""
        self._const_data: Dict[str, EmulatorConstantData] = {}

    def set_emulator_const_data(self, data: Dict[str, EmulatorConstantData]) -> None:
        """
        设置模拟器配置数据。

        参数：
            data: 将模拟器名称映射到其常量配置的字典。
        """
        self._const_data = data

    def find(self) -> List[AdbDevice]:
        """
        从正在运行的模拟器和系统 ADB 中查找所有 ADB 设备。

        这是主要入口点。它：
        1. 通过进程扫描检测运行中的模拟器
        2. 解析每个模拟器的 ADB 路径
        3. 枚举设备序列号
        4. 应用模拟器特定的配置
        5. 还检查系统 PATH 中的 adb 可执行文件

        返回：
            已配置的 AdbDevice 对象列表。
        """
        logger.info("正在查找 ADB 设备...")
        result: List[AdbDevice] = []

        for emulator in self._find_emulators():
            adb_path = self._get_adb_path(emulator.const_data, emulator.process.pid)
            if not adb_path or not adb_path.exists():
                continue

            serials = self.find_adb_serials(adb_path, emulator)
            for ser in serials:
                dev = AdbDevice(
                    name=emulator.name,
                    adb_path=adb_path,
                    serial=ser,
                    screencap_methods=ScreencapMethod.default(),
                    input_methods=InputMethod.default(),
                    config={},
                )
                self.request_device_config(emulator, dev)
                result.append(dev)

        # 还检查系统 PATH 中的 adb
        env_adb = shutil.which("adb")
        if env_adb and Path(env_adb).exists():
            result.extend(self.find_specified(Path(env_adb)))

        logger.info(f"找到 {len(result)} 个设备")
        return result

    def find_specified(self, adb_path: Path) -> List[AdbDevice]:
        """
        使用指定的 ADB 可执行文件路径查找设备。

        参数：
            adb_path: ADB 可执行文件的路径。

        返回：
            通过此 ADB 路径找到的 AdbDevice 对象列表。
        """
        serials = self._find_serials_by_adb_command(adb_path)
        result: List[AdbDevice] = []

        for ser in serials:
            dev = AdbDevice(
                name=str(adb_path),
                adb_path=adb_path,
                serial=ser,
                screencap_methods=ScreencapMethod.default(),
                input_methods=InputMethod.default(),
                config={},
            )
            # 即使没有模拟器信息也尝试检测设备特定配置
            self.request_device_config(
                Emulator("", ProcessInfo(), EmulatorConstantData("")), dev
            )
            result.append(dev)

        return result

    def find_adb_serials(self, adb_path: Path, emulator: Emulator) -> List[str]:
        """
        查找特定模拟器的 ADB 设备序列号。

        应用模拟器特定的逻辑：
        - LDPlayer: 使用标准 adb devices
        - MuMu12/v5: 使用 MuMuManager.exe 工具
        - 其他: 默认行为（常见序列号 + adb devices）

        参数：
            adb_path: ADB 可执行文件的路径。
            emulator: 模拟器实例。

        返回：
            可用设备序列字符串列表。
        """
        if emulator.name == "LDPlayer":
            return self._find_serials_by_adb_command(adb_path)
        elif emulator.name in ("MuMuPlayer12", "MuMuPlayer12 v5"):
            return self._find_mumu_serials(adb_path)
        else:
            return self._default_find_adb_serials(adb_path, emulator)

    def request_device_config(self, emulator: Emulator, device: AdbDevice) -> None:
        """
        应用模拟器特定的设备配置。

        为以下功能配置特殊特性：
        - Waydroid: 自定义应用程序启动命令
        - MuMuPlayer12: 带路径和索引的模拟器额外功能
        - MuMuPlayer12 v5: 类似于 MuMu12，但目录结构不同
        - LDPlayer: 带路径、索引和 PID 的模拟器额外功能

        参数：
            emulator: 模拟器实例（对于通用设备可能为空）。
            device: 要配置的 AdbDevice（就地修改）。
        """
        # Waydroid 配置（跨平台）
        if self._request_waydroid_config(device):
            return

        # 模拟器特定的额外功能
        if emulator.name == "MuMuPlayer12":
            path_opt = self._get_process_path(emulator.process.pid)
            if not path_opt:
                return
            # C++ 使用 parent().parent()
            dir_path = path_opt.parent.parent if path_opt.parent else path_opt

            mumu_cfg = device.config.setdefault("extras", {}).setdefault("mumu", {})
            mumu_cfg["enable"] = True
            mumu_cfg["path"] = str(dir_path)
            mumu_cfg["index"] = self._get_mumu_index(device.serial)

            device.screencap_methods = int(ScreencapMethod.EMULATOR_EXTRAS)
            device.input_methods = InputMethod.default() | int(
                InputMethod.EMULATOR_EXTRAS
            )

            logger.info(f"MuMuPlayer12 配置 serial={device.serial} cfg={device.config}")

        elif emulator.name == "MuMuPlayer12 v5":
            path_opt = self._get_process_path(emulator.process.pid)
            if not path_opt:
                return
            # C++ 使用 parent().parent().parent().parent()
            dir_path = path_opt
            for _ in range(4):
                dir_path = dir_path.parent if dir_path.parent != dir_path else dir_path

            mumu_cfg = device.config.setdefault("extras", {}).setdefault("mumu", {})
            mumu_cfg["enable"] = True
            mumu_cfg["path"] = str(dir_path)
            mumu_cfg["index"] = self._get_mumu_index(device.serial)

            device.screencap_methods = int(ScreencapMethod.EMULATOR_EXTRAS)
            device.input_methods = InputMethod.default() | int(
                InputMethod.EMULATOR_EXTRAS
            )

            logger.info(
                f"MuMuPlayer12 v5 配置 serial={device.serial} cfg={device.config}"
            )

        elif emulator.name == "LDPlayer":
            path_opt = self._get_process_path(emulator.process.pid)
            if not path_opt:
                return
            dir_path = path_opt.parent

            ld_cfg = device.config.setdefault("extras", {}).setdefault("ld", {})
            ld_cfg["enable"] = True
            ld_cfg["path"] = str(dir_path)
            ld_cfg["index"] = self._get_ld_index(device.serial)
            ld_cfg["pid"] = emulator.process.pid

            device.screencap_methods = int(ScreencapMethod.EMULATOR_EXTRAS)
            device.input_methods = InputMethod.default()

            logger.info(f"LDPlayer 配置 serial={device.serial} cfg={device.config}")

    # ----- 内部辅助方法 -----
    def _default_find_adb_serials(
        self, adb_path: Path, emulator: Emulator
    ) -> List[str]:
        """
        默认序列号发现：将常见序列号与 adb devices 输出结合。

        参数：
            adb_path: ADB 可执行文件的路径。
            emulator: 模拟器实例。

        返回：
            可用序列号列表（去重并验证连接性）。
        """
        serials = list(emulator.const_data.adb_common_serials)
        requested = self._find_serials_by_adb_command(adb_path)
        serials.extend(requested)

        # 去重同时保持顺序
        seen: set[str] = set()
        serials = [s for s in serials if not (s in seen or seen.add(s))]  # type: ignore

        # 检查可用性
        return self._check_available_adb_serials(adb_path, serials)

    def _find_serials_by_adb_command(self, adb_path: Path) -> List[str]:
        """
        通过 'adb devices' 命令获取设备序列号。

        参数：
            adb_path: ADB 可执行文件的路径。

        返回：
            设备序列字符串列表。
        """
        cu = AdbControlUnit(str(adb_path), "")
        return cu.find_device()

    def _request_adb_connect(self, adb_path: Path, serial: str) -> bool:
        """
        尝试连接到设备并验证 shell 访问。

        参数：
            adb_path: ADB 可执行文件的路径。
            serial: 设备序列字符串。

        返回：
            如果连接成功则返回 True，否则返回 False。
        """
        cu = AdbControlUnit(str(adb_path), serial)
        return cu.connect()

    def _check_available_adb_serials(
        self, adb_path: Path, serials: List[str]
    ) -> List[str]:
        """
        过滤序列号，仅保留可连接的序列号。

        参数：
            adb_path: ADB 可执行文件的路径。
            serials: 要检查的序列号列表。

        返回：
            可访问的序列号列表。
        """
        available: List[str] = []
        for ser in serials:
            if self._request_adb_connect(adb_path, ser):
                available.append(ser)
        return available

    def _request_waydroid_config(self, device: AdbDevice) -> bool:
        """
        检测 Waydroid 并应用自定义配置。

        Waydroid 由于其独特的架构需要特殊的应用启动命令。

        参数：
            device: 要配置的 AdbDevice（如果检测到 Waydroid 则就地修改）。

        返回：
            如果检测到 Waydroid 并已配置则返回 True，否则返回 False。
        """
        cu = AdbControlUnit(str(device.adb_path), device.serial)
        ok, out = cu.shell("getprop | grep ro.product.brand")

        if not ok or "waydroid" not in out:
            return False

        command = device.config.setdefault("command", {})
        command["StartApp"] = [
            "{ADB}",
            "-s",
            "{ADB_SERIAL}",
            "shell",
            "monkey -p {INTENT} --pct-syskeys 0 1",
        ]
        command["StartActivity"] = [
            "{ADB}",
            "-s",
            "{ADB_SERIAL}",
            "shell",
            "am start -n {INTENT} --windowingMode 4",
        ]

        logger.info(
            f"检测到 Waydroid adb_path={device.adb_path} serial={device.serial} "
            f"config={device.config}"
        )
        return True

    def _find_emulators(self) -> List[Emulator]:
        """
        扫描正在运行的进程以检测模拟器。

        返回：
            检测到的 Emulator 实例列表。
        """
        procs = self._list_processes()
        result: List[Emulator] = []

        for proc in procs:
            for name, const in self._const_data.items():
                if const.keyword and const.keyword in proc.name:
                    result.append(Emulator(name=name, process=proc, const_data=const))
                    break

        logger.debug(f"模拟器: {result}")
        return result

    def _get_adb_path(
        self, emulator_data: EmulatorConstantData, pid: int
    ) -> Optional[Path]:
        """
        解析模拟器进程的 ADB 可执行文件路径。

        参数：
            emulator_data: 带有候选路径的模拟器配置。
            pid: 模拟器的进程 ID。

        返回：
            如果找到则返回 ADB 可执行文件的路径，否则返回 None。
        """
        exe_path = self._get_process_path(pid)
        if not exe_path:
            return None

        base_dir = exe_path.parent
        for rel in emulator_data.adb_candidate_paths:
            adb_path = (base_dir / rel).resolve()
            if adb_path.exists():
                return adb_path

        return None

    @staticmethod
    def _list_processes() -> List[ProcessInfo]:
        """
        列出系统上所有正在运行的进程。

        返回：
            带有 PID 和名称的 ProcessInfo 对象列表。
        """
        import psutil

        procs: List[ProcessInfo] = []
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                info = proc.info
                name = info.get("name") or ""
                procs.append(ProcessInfo(pid=int(info.get("pid", 0)), name=name))
        except Exception as e:
            logger.debug(f"list_processes 错误: {e}")
        return procs

    @staticmethod
    def _get_process_path(pid: int) -> Optional[Path]:
        """
        通过 PID 获取进程的可执行文件路径。

        参数：
            pid: 进程 ID。

        返回：
            进程可执行文件的路径，如果无法访问则返回 None。
        """
        import psutil

        try:
            proc = psutil.Process(pid)
            return Path(proc.exe())
        except Exception:
            return None

    @staticmethod
    def _get_mumu_index(adb_serial: str) -> int:
        """
        从 ADB 序列号计算 MuMu 模拟器实例索引。

        MuMu 使用基于端口的索引：index = (port - 16384) / 32

        参数：
            adb_serial: 序列号字符串，如 "127.0.0.1:16416"。

        返回：
            实例索引（从 0 开始），如果解析失败则返回 0。
        """
        try:
            if ":" not in adb_serial:
                return 0
            port = int(adb_serial.split(":", 1)[1])
            return (port - 16384) // 32
        except Exception:
            return 0

    @staticmethod
    def _get_ld_index(adb_serial: str) -> int:
        """
        从 ADB 序列号计算 LDPlayer 模拟器实例索引。

        LDPlayer 使用模拟器风格的序列号：index = (port - 5554) / 2

        参数：
            adb_serial: 序列号字符串，如 "emulator-5556"。

        返回：
            实例索引（从 0 开始），如果解析失败则返回 0。
        """
        try:
            if "-" not in adb_serial:
                return 0
            port = int(adb_serial.split("-", 1)[1])
            return (port - 5554) // 2
        except Exception:
            return 0

    @staticmethod
    def _find_mumu_serials(adb_path: Path) -> List[str]:
        """
        使用 MuMuManager.exe 工具查找 MuMu 设备序列号。

        MuMuManager 提供包含设备 IP 和端口信息的 JSON 输出。
        如果找不到 MuMuManager 则回退到 'adb devices'。

        参数：
            adb_path: ADB 可执行文件的路径（用于定位 MuMuManager）。

        返回：
            "ip:port" 格式的序列号字符串列表。
        """
        mgr = (adb_path.parent / "MuMuManager.exe").resolve()

        if not mgr.exists():
            logger.warning(f"未找到 MuMuManager: {mgr}，回退到 adb devices")
            cu = AdbControlUnit(str(adb_path), "")
            return cu.find_device()

        try:
            args = [str(mgr), "info", "--vmindex", "all"]
            result = subprocess.run(
                args, capture_output=True, text=True, timeout=20, check=False
            )
            data = json.loads(result.stdout)
        except Exception as e:
            logger.error(f"解析 MuMuManager 输出失败: {e}")
            return []

        def to_serial(obj: dict) -> Optional[str]:
            """将 MuMuManager JSON 对象转换为序列号字符串。"""
            ip = obj.get("adb_host_ip")
            port = obj.get("adb_port")
            if isinstance(ip, str) and isinstance(port, int):
                return f"{ip}:{port}"
            return None

        serials: List[str] = []

        # 情况 1: 单个设备（直接对象）
        if isinstance(data, dict):
            serial = to_serial(data)
            if serial:
                return [serial]

            # 情况 2: 多个设备（对象的对象）
            for value in data.values():
                if isinstance(value, dict):
                    serial = to_serial(value)
                    if serial:
                        serials.append(serial)

        return serials


# ---------- CLI 演示 ----------
def main() -> None:
    """
    用于测试 ADB 设备发现的命令行界面。

    检测平台，加载适当的模拟器配置，
    并显示所有发现的设备及其详细信息。
    """
    finder = AdbDeviceFinder()
    emulator_data = EmulatorConfig.get_platform_config()
    finder.set_emulator_const_data(emulator_data)

    print("正在搜索 ADB 设备...")
    print(f"平台: {platform.system()}")
    print(f"支持的模拟器: {', '.join(emulator_data.keys())}\n")

    devices = finder.find()
    print(f"\n找到 {len(devices)} 个设备:")

    for i, device in enumerate(devices, 1):
        print(f"\n{i}. {device.name}")
        print(f"   ADB 路径: {device.adb_path}")
        print(f"   序列号: {device.serial}")
        print(f"   截屏方法: {device.screencap_methods}")
        print(f"   输入方法: {device.input_methods}")
        if device.config:
            print(f"   配置: {json.dumps(device.config, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
