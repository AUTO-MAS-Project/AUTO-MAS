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
import psutil
import asyncio
import win32gui
import win32con
import win32process
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.models.emulator import DeviceStatus, DeviceInfo, DeviceBase
from app.models.config import EmulatorConfig
from app.utils import ProcessRunner, get_logger


logger = get_logger("MuMu模拟器管理")


class MumuManager(DeviceBase):
    """
    基于MuMuManager.exe的模拟器管理
    """

    def __init__(self, config: EmulatorConfig) -> None:
        if not (Path(config.get("Info", "Path"))).exists():
            raise FileNotFoundError(
                f"MuMuManager.exe文件不存在: {config.get('Info', 'Path')}"
            )

        if config.get("Data", "Type") != "mumu":
            raise ValueError("配置的模拟器类型不是mumu")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        logger.info(f"开始启动模拟器 {idx}  - {package_name}")

        from app.core import Config

        status = DeviceStatus.UNKNOWN  # 初始化status变量
        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if status == DeviceStatus.ONLINE:
                return (await self.getInfo(idx))[idx]
            elif status == DeviceStatus.OFFLINE:
                break
            await asyncio.sleep(0.1)

        else:
            raise RuntimeError(f"模拟器 {idx} 无法启动, 当前状态码: {status}")

        if_close_mumu_nx = await self.find_mumu_nx_window() is None

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "launch",
            *(["-pkg", package_name] if package_name else []),
            timeout=self.config.get("Data", "MaxWaitTime"),
            if_merge_std=True,
        )
        # 参考命令 MuMuManager.exe control -v 2 launch

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if if_close_mumu_nx:
                if_close_mumu_nx = not await self.close_mumu_nx_window()
            if Config.get("Function", "IfSilence") and status == DeviceStatus.STARTING:
                await self.setVisible(idx, False)
            elif status == DeviceStatus.ONLINE:
                await asyncio.sleep(
                    30
                    if package_name != ""
                    and self.config.get("Data", "MaxWaitTime") > 60
                    else 3
                )  # 等待模拟器的 ADB 等服务完全启动, 低性能设备额外等待应用启动
                return (await self.getInfo(idx))[idx]
            await asyncio.sleep(0.1)
        else:
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器 {idx} 启动失败, 状态码: {status}")
            raise RuntimeError(f"模拟器 {idx} 启动超时, 当前状态码: {status}")

    async def close(self, idx: str) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            return status

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "shutdown",
            timeout=self.config.get("Data", "MaxWaitTime"),
            if_merge_std=True,
        )
        # 参考命令 MuMuManager.exe control -v 2 shutdown

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if status == DeviceStatus.OFFLINE:
                return DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)

        else:
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器 {idx} 关闭失败, 状态码: {status}")
            raise RuntimeError(f"模拟器 {idx} 关闭超时, 当前状态码: {status}")

    async def getStatus(self, idx: str, data: str | None = None) -> DeviceStatus:
        if data is None:
            try:
                data = await self.get_device_info(idx)
            except Exception as e:
                logger.error(f"获取模拟器 {idx} 信息失败: {e}")
                return DeviceStatus.ERROR
        try:
            data_json = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return DeviceStatus.UNKNOWN

        if data_json["is_android_started"]:
            return DeviceStatus.ONLINE
        elif data_json["is_process_started"]:
            return DeviceStatus.STARTING
        else:
            return DeviceStatus.OFFLINE

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        data = await self.get_device_info(idx or "all")

        data_json = json.loads(data)

        result: dict[str, DeviceInfo] = {}

        if not data_json:
            return result

        if isinstance(data_json, dict) and "index" in data_json and "name" in data_json:
            index = data_json["index"]
            name = data_json["name"]
            status = await self.getStatus(index, data)
            adb_address = (
                f"{data_json.get('adb_host_ip')}:{data_json.get('adb_port')}"
                if data_json.get("adb_host_ip", None)
                and data_json.get("adb_port", None)
                else "Unknown"
            )
            result[index] = DeviceInfo(
                title=name, status=status, adb_address=adb_address
            )

        elif isinstance(data_json, dict):
            for value in data_json.values():
                if isinstance(value, dict) and "index" in value and "name" in value:
                    index = value["index"]
                    name = value["name"]
                    status = await self.getStatus(index)
                    adb_address = (
                        f"{value.get('adb_host_ip')}:{value.get('adb_port')}"
                        if value.get("adb_host_ip", None)
                        and value.get("adb_port", None)
                        else "Unknown"
                    )
                    result[index] = DeviceInfo(
                        title=name, status=status, adb_address=adb_address
                    )

        return result

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.STARTING, DeviceStatus.ONLINE]:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "show_window" if is_visible else "hide_window",
            timeout=self.config.get("Data", "MaxWaitTime"),
            if_merge_std=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")

        return await self.getStatus(idx)

    async def get_device_info(self, idx: str) -> str:
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "info",
            "-v",
            idx,
            timeout=self.config.get("Data", "MaxWaitTime"),
            if_merge_std=True,
        )
        if result.returncode != 0:
            logger.error(f"获取模拟器 {idx} 信息失败: {result.stdout.strip()}")
            raise RuntimeError(f"命令执行失败: {result.stdout.strip()}")

        return result.stdout.strip()

    async def find_mumu_nx_window(self) -> int | None:
        """
        查找 MuMu 多开器窗口

        Returns:
            int | None: 窗口句柄，未找到返回 None
        """

        def enum_cb(hwnd: int, result_list: list[int | None]) -> bool:
            if result_list[0] is not None:
                return False  # 已找到，停止枚举
            if not win32gui.IsWindowVisible(hwnd) or win32gui.GetParent(hwnd) != 0:
                return True
            if win32gui.GetWindowText(hwnd) != "MuMu模拟器":
                return True
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                proc_name = psutil.Process(pid).name().lower()
                if proc_name == "mumunxmain.exe":
                    result_list[0] = hwnd
                    return False
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
            return True

        result: list[int | None] = [None]
        with suppress(Exception):
            # EnumWindows 在回调返回 False 时抛出异常，属正常行为
            win32gui.EnumWindows(enum_cb, result)
        return result[0]

    async def close_mumu_nx_window(self) -> bool:
        """
        关闭 MuMu 多开器窗口
        """

        hwnd = await self.find_mumu_nx_window()
        if hwnd is not None:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            logger.success("已关闭 MuMuNX 窗口")
            return True
        return False
