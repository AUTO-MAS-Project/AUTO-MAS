#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import re
import json
import shlex
import win32gui
import asyncio
import keyboard
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from app.utils.ProcessManager import ProcessManager
from app.models.emulator import DeviceStatus, DeviceBase, DeviceInfo
from app.models.config import EmulatorConfig
from app.utils import get_logger

logger = get_logger("通用模拟器管理")


class GeneralDeviceManager(DeviceBase):
    """
    用于管理一般应用程序进程
    """

    def __init__(self, config: EmulatorConfig) -> None:

        if not Path(config.get("Info", "Path")).exists():
            raise FileNotFoundError(f"模拟器文件不存在: {config.get('Info', 'Path')}")

        if config.get("Data", "Type") != "general":
            raise ValueError("配置的模拟器类型不是通用类型")

        self.config = config
        self.emulator_path = Path(config.get("Info", "Path"))
        self.process_managers: Dict[str, ProcessManager] = {}
        self.device_info: Dict[str, Dict[str, Any]] = {}

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
        await self.process_managers[idx].open_process(self.emulator_path, *args)

        # 等待进程启动
        await asyncio.sleep(self.config.get("Data", "MaxWaitTime"))

        return (await self.getInfo(idx))[idx]

    async def close(self, idx: str) -> DeviceStatus:

        status = await self.getStatus(idx)
        if status == DeviceStatus.OFFLINE:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            return status

        # 终止进程
        await self.process_managers[idx].kill()

        # 等待进程完全停止
        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
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

        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):

            # 检查窗口可见性是否符合预期
            if self.process_managers[idx].main_pid is not None and (
                win32gui.IsWindowVisible(self.process_managers[idx].main_pid)
                == is_visible
            ):
                return status

            try:
                keyboard.press_and_release(
                    "+".join(
                        _.strip().lower()
                        for _ in json.loads(self.config.get("Data", "BossKey"))
                    )
                )  # 老板键
            except Exception as e:
                logger.error(f"发送BOSS键失败: {e}")

            await asyncio.sleep(0.5)

        else:
            raise RuntimeError(f"隐藏设备{idx}窗口超时")

    def parse_index(self, idx: str):

        if "|" not in idx:
            raise ValueError("缺少 '|' 分隔符")

        cmd_part, addr_part = idx.split("|", 1)
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
        self.device_info.clear()

        logger.info("设备管理器资源清理完成")
