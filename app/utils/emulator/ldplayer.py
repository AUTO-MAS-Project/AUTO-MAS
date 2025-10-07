#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025 AUTO-MAS Team

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


import json
import asyncio
import psutil
import keyboard
import subprocess
import win32gui
from pydantic import BaseModel
from pathlib import Path
from typing import Literal

from app.models.emulator import DeviceStatus, DeviceBase
from app.models.config import EmulatorConfig
from app.utils.logger import get_logger

logger = get_logger("雷电模拟器管理")


class EmulatorInfo(BaseModel):
    idx: int
    title: str
    top_hwnd: int
    bind_hwnd: int
    in_android: int
    pid: int
    vbox_pid: int
    width: int
    height: int
    density: int


class LDManager(DeviceBase):
    """
    基于dnconsole.exe的模拟器管理
    """

    def __init__(self, config: EmulatorConfig) -> None:

        if not Path(config.get("Info", "Path")).exists():
            raise FileNotFoundError(
                f"MuMuManager.exe文件不存在: {config.get('Info', 'Path')}"
            )

        if config.get("Data", "Type") != "mumu":
            raise ValueError("配置的模拟器类型不是mumu")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    async def open(self, idx: str, package_name="") -> tuple[bool, int, dict]:
        """
        启动指定模拟器
        Returns:
            tuple[bool, int, str]: 是否成功, 当前状态码, ADB端口信息
        """
        Ok, info, status = await self.get_device_info(idx)
        if status != DeviceStatus.OFFLINE:
            logger.error(
                f"模拟器{idx}未处于关闭状态，当前状态码: {status}, 需求状态码: {DeviceStatus.OFFLINE}"
            )
            return False, status, {}

        result = subprocess.run(
            (
                [
                    self.emulator_path,
                    "launch",
                    "--index",
                    idx,
                    "--packagename",
                    f'"{package_name}"',
                ]
                if package_name
                else [self.emulator_path, "launch", "--index", idx]
            ),
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )

        # 参考命令 dnconsole.exe launch --index 0
        logger.debug(f"启动结果:{result}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        for _ in range(self.config.get("Info", "MaxWaitTime") * 10):

            Ok, info, status = await self.get_device_info(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                logger.error(f"模拟器{idx}启动失败，状态码: {status}")
                return False, status, {}
            if status == DeviceStatus.ONLINE:
                logger.debug(info)
                if Ok and isinstance(info, EmulatorInfo):
                    pid: int = info.vbox_pid
                    adb_port = ""
                    adb_host_ip = await self.get_adb_ports(pid)
                    print(adb_host_ip)
                    if adb_host_ip:
                        return (
                            True,
                            status,
                            {"adb_port": adb_port, "adb_host_ip": adb_host_ip},
                        )

                return True, status, {}
            await asyncio.sleep(0.1)

        return False, DeviceStatus.UNKNOWN, {}

    async def close(self, idx: str) -> tuple[bool, int]:
        """
        关闭指定模拟器
        Returns:
            - tuple[bool, int]: 是否成功, 当前状态码

        参考命令行:dnconsole.exe quit --index 0
        """
        Ok, info, status = await self.get_device_info(idx)
        if status != DeviceStatus.ONLINE and status != DeviceStatus.STARTING:
            return False, DeviceStatus.NOT_FOUND

        result = subprocess.run(
            [self.emulator_path, "quit", "--index", idx],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )

        # 参考命令 dnconsole.exe quit --index 0
        if result.returncode != 0:
            return True, DeviceStatus.OFFLINE

        for _ in range(self.config.get("Info", "MaxWaitTime") * 10):
            Ok, info, status = await self.get_device_info(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                return False, status
            if status == DeviceStatus.OFFLINE:
                return True, DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)

        return False, DeviceStatus.UNKNOWN

    async def get_status(self, idx: str) -> int:
        """
        获取指定模拟器当前状态
        返回值: 状态码
        """
        _, _, status = await self.get_device_info(idx)
        return status

    async def get_device_info(
        self,
        idx: str,
        data: dict[int, EmulatorInfo] | None = None,
    ) -> tuple[Literal[True], EmulatorInfo, int] | tuple[Literal[False], dict, int]:
        """
        获取指定模拟器的信息和状态
        Returns:
            - tuple[bool, EmulatorInfo | dict, int]: 是否成功, 模拟器信息或空字典, 状态码

        参考命令行:dnconsole.exe list2
        """
        if not data:
            result = await self._get_all_info()
        else:
            result = data

        try:
            emulator_info = result.get(int(idx))
            print(emulator_info)
            if not emulator_info:
                logger.error(f"未找到模拟器{idx}的信息")
                return False, {}, DeviceStatus.UNKNOWN

            logger.debug(f"获取模拟器{idx}信息: {emulator_info}")

            # 计算状态码
            if emulator_info.in_android == 1:
                status = DeviceStatus.ONLINE
            elif emulator_info.in_android == 2:
                if emulator_info.vbox_pid > 0:
                    status = DeviceStatus.STARTING
                    # 雷电启动后, vbox_pid为-1, 目前不知道有什么区别
                else:
                    status = DeviceStatus.STARTING
            elif emulator_info.in_android == 0:
                status = DeviceStatus.OFFLINE
            else:
                status = DeviceStatus.UNKNOWN

            logger.debug(f"获取模拟器{idx}状态: {status}")
            return True, emulator_info, status
        except:  # noqa: E722
            logger.error(f"获取模拟器{idx}信息失败")
            return False, {}, DeviceStatus.UNKNOWN

    async def _get_all_info(self) -> dict[int, EmulatorInfo]:

        result = subprocess.run(
            [self.emulator_path, "list2"],
            capture_output=True,
            text=True,
            encoding="gbk",
            errors="replace",
        )

        # logger.debug(f"全部信息{result.stdout.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        emulators: dict[int, EmulatorInfo] = {}
        data = result.stdout.strip()

        for line in data.strip().splitlines():
            parts = line.strip().split(",")
            if len(parts) != 10:
                raise ValueError(f"数据格式错误: {line}")
            try:
                info = EmulatorInfo(
                    idx=int(parts[0]),
                    title=parts[1],
                    top_hwnd=int(parts[2]),
                    bind_hwnd=int(parts[3]),
                    in_android=int(parts[4]),
                    pid=int(parts[5]),
                    vbox_pid=int(parts[6]),
                    width=int(parts[7]),
                    height=int(parts[8]),
                    density=int(parts[9]),
                )
                emulators[info.idx] = info
            except Exception as e:
                logger.warning(f"解析失败: {line}, 错误: {e}")
                pass
        return emulators

    # ?wk雷电你都返回了什么啊

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        """
        解析_emulator_info字典，提取idx和title，便于前端显示
        """
        raw_data = await self._get_all_info()
        result: dict[str, dict[str, str]] = {}
        for info in raw_data.values():
            Ok, device_info, status = await self.get_device_info(
                str(info.idx), raw_data
            )
            result[str(info.idx)] = {"title": info.title, "status": str(status)}
        return result

    async def hide_device(self, idx: str) -> tuple[bool, int]:
        """隐藏设备窗口"""
        Ok, result, status = await self.get_device_info(idx)
        if not Ok or not isinstance(result, EmulatorInfo):
            return False, DeviceStatus.UNKNOWN
        if status != DeviceStatus.ONLINE:
            return False, status

        try:

            for _ in range(2):
                # 使用键盘工具发送按键组合
                keyboard.press_and_release(
                    "+".join(
                        _.strip().lower()
                        for _ in json.loads(self.config.get("Info", "BossKeys"))
                    )
                )

                # 等待系统处理
                await asyncio.sleep(0.5)

                # 检查窗口可见性是否符合预期
                current_visible = win32gui.IsWindowVisible(result.top_hwnd)

                if current_visible == False:
                    return True, status

        except Exception as e:
            logger.error(f"发送BOSS键失败: {e}")

        return False, status

    async def show_device(self, idx: str) -> tuple[bool, int]:
        """显示设备窗口"""
        OK, result, status = await self.get_device_info(idx)
        if not OK or not isinstance(result, EmulatorInfo):
            return False, DeviceStatus.UNKNOWN
        if status != DeviceStatus.ONLINE:
            return False, status

        try:

            for _ in range(2):
                # 使用键盘工具发送按键组合
                keyboard.press_and_release(
                    "+".join(
                        _.strip().lower()
                        for _ in json.loads(self.config.get("Info", "BossKeys"))
                    )
                )

                # 等待系统处理
                await asyncio.sleep(0.5)

                # 检查窗口可见性是否符合预期
                current_visible = win32gui.IsWindowVisible(result.top_hwnd)

                if current_visible == True:
                    return True, status

        except Exception as e:
            logger.error(f"发送BOSS键失败: {e}")

        return False, status

    async def get_adb_ports(self, pid: int) -> int:
        """使用psutil获取adb端口"""
        try:
            process = psutil.Process(pid)
            connections = process.net_connections(kind="inet")
            for conn in connections:
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port != 2222:
                    return conn.laddr.port
            return 0  # 如果没有找到合适的端口，返回0
        except:  # noqa: E722
            return 0
