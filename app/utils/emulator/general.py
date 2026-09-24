#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
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


import asyncio
import re
import shlex
import time
from pathlib import Path
from typing import Dict

import psutil

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase, DeviceInfo, DeviceStatus
from app.utils import get_logger
from app.utils.platform import IS_WINDOWS
from app.utils.platform import window as platform_window
from app.utils.ProcessManager import ProcessManager, get_main_window_handle

logger = get_logger("通用模拟器管理")


class GeneralDeviceManager(DeviceBase):
    """
    用于管理一般应用程序进程
    """

    def __init__(self, config: EmulatorConfig) -> None:

        if not Path(config.get("Info", "Path")).exists():
            raise FileNotFoundError(f"模拟器文件不存在: {config.get('Info', 'Path')}")

        if config.get("Info", "Type") != "general":
            raise ValueError("配置的模拟器类型不是通用类型")

        self.config = config
        self.emulator_path = Path(config.get("Info", "Path"))
        self.process_managers: Dict[str, ProcessManager] = {}

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:

        # 检查是否已经在运行
        current_status = await self.getStatus(idx)
        if current_status == DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}已经在运行，状态: {current_status}")
            return (await self.getInfo(idx))[idx]

        # 创建进程管理器
        if idx not in self.process_managers:
            self.process_managers[idx] = ProcessManager()

        args, _ = self.parse_index(idx)

        # 启动进程
        await self.process_managers[idx].open_process(
            self.emulator_path, *args, breakaway=True
        )

        # 等待进程启动
        await asyncio.sleep(self.config.get("Info", "MaxWaitTime"))

        return (await self.getInfo(idx))[idx]

    async def close(self, idx: str) -> DeviceStatus:

        status = await self.getStatus(idx)
        if status == DeviceStatus.OFFLINE:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            return status

        # 终止进程
        await self.process_managers[idx].kill()

        # 等待进程完全停止
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            if not await self.process_managers[idx].is_running():
                return DeviceStatus.OFFLINE

            await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"关闭设备{idx}超时")

    async def getStatus(self, idx: str) -> DeviceStatus:

        if idx not in self.process_managers:
            return DeviceStatus.OFFLINE

        if await self.process_managers[idx].is_running():
            return DeviceStatus.ONLINE
        else:
            return DeviceStatus.OFFLINE

    async def list_devices(self) -> dict[str, str]:
        return {}

    async def getInfo(self, idx: str | None) -> Dict[str, DeviceInfo]:

        data = {}
        for index in self.process_managers:
            if idx is not None and index != idx:
                continue
            data[index] = DeviceInfo(
                title=f"{self.config.get('Info', 'Name')}_{index}",
                status=await self.getStatus(index),
                adb_address=self.parse_index(index)[1],
            )
        return data

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:

        if not IS_WINDOWS:
            raise RuntimeError("切换模拟器窗口可见性仅支持 Windows 平台")

        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        # 按本实例进程树的窗口句柄精确切换, 不发全局老板键:
        # 老板键不带实例信息, 多开时会把别的实例一起翻过去 (#948)
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            hwnd = self._find_window(idx)
            if hwnd is None:
                # 窗口可能还没建出来, 等一会儿重新查找
                await asyncio.sleep(0.5)
                continue

            # 检查窗口可见性是否符合预期
            if platform_window.is_visible(hwnd) == is_visible:
                return status

            try:
                if is_visible:
                    platform_window.show_window(hwnd)
                else:
                    platform_window.hide_window(hwnd)
            except Exception as e:
                logger.error(f"切换设备{idx}窗口可见性失败: {e}")

            await asyncio.sleep(0.5)

        else:
            raise RuntimeError(f"隐藏设备{idx}窗口超时")

    def _find_window(self, idx: str) -> int | None:
        """在本实例启动的进程及其子孙进程里找主窗口句柄。

        模拟器常由启动器派生子进程再建窗口, 只看启动进程会找不到。
        各进程先各取一个主窗口, 再按「可见优先、面积次之」挑一个;
        启动器已退出、窗口挂在别的进程名下时找不到, 返回 None。
        """

        main_pid = self.process_managers[idx].main_pid
        if main_pid is None:
            return None

        pids = [main_pid]
        try:
            pids.extend(
                child.pid for child in psutil.Process(main_pid).children(recursive=True)
            )
        except psutil.Error:
            pass

        best_hwnd: int | None = None
        best_score: tuple[bool, int] | None = None
        for pid in pids:
            hwnd = get_main_window_handle(pid)
            if hwnd is None:
                continue
            try:
                left, top, right, bottom = platform_window.get_window_rect(hwnd)
                score = (
                    platform_window.is_visible(hwnd),
                    max(0, right - left) * max(0, bottom - top),
                )
            except Exception:
                continue
            if best_score is None or score > best_score:
                best_hwnd, best_score = hwnd, score

        return best_hwnd

    def parse_index(self, idx: str):

        if "|" not in idx:
            raise ValueError("缺少 '|' 分隔符")

        cmd_part, addr_part = idx.rsplit("|", 1)
        args = shlex.split(cmd_part.strip())

        addr = addr_part.replace("：", ":").replace("。", ".")
        addr = re.sub(r"\s+", "", addr)

        if addr in {"usb", "local", "shell"} or addr.startswith("emulator-"):
            return args, addr

        if ":" not in addr:
            raise ValueError(f"ADB 地址缺少端口: {addr}")

        i = addr.rfind(":")
        host, port_str = addr[:i], addr[i + 1 :]

        if not port_str.isdigit() or not (1 <= int(port_str) <= 65535):
            raise ValueError(f"无效端口: {port_str}")
        if not host:
            raise ValueError("主机名为空")

        return args, f"{host}:{port_str}"

    async def cleanup(self) -> None:
        """
        清理所有资源
        """
        logger.info("开始清理设备管理器资源")

        for idx, pm in self.process_managers.items():
            try:
                if await pm.is_running():
                    await pm.kill()
            except Exception as e:
                logger.error(f"清理设备{idx}资源失败: {str(e)}")

        self.process_managers.clear()

        logger.info("设备管理器资源清理完成")
