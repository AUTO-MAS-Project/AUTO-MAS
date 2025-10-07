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
import subprocess
from pathlib import Path


from app.models.emulator import DeviceStatus, DeviceBase
from app.models.config import EmulatorConfig
from app.utils.logger import get_logger


logger = get_logger("MuMu模拟器管理")


class MumuManager(DeviceBase):
    """
    基于MuMuManager.exe的模拟器管理
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

    async def open(self, idx: str, package_name: str = "") -> tuple[bool, int, dict]:
        """
        启动指定模拟器

        Parameters
        ----------
        idx : str
            模拟器序号
        package_name : str, optional
            启动指定包名, by default ""

        Returns
        -------
        tuple[bool, int, dict]
            是否成功, 当前状态码, 设备信息
        """

        status = await self.get_status(idx)
        if status != DeviceStatus.OFFLINE:
            logger.error(
                f"模拟器{idx}未处于关闭状态，当前状态码: {status}, 需求状态码: {DeviceStatus.OFFLINE}"
            )
            return False, status, {}

        result = subprocess.run(
            (
                [
                    self.emulator_path,
                    "control",
                    "-v",
                    idx,
                    "launch",
                    "-pkg",
                    package_name,
                ]
                if package_name
                else [self.emulator_path, "control", "-v", idx, "launch"]
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 参考命令 MuMuManager.exe control -v 2 launch
        logger.debug(f"启动结果:{result}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        for _ in range(self.config.get("Info", "MaxWaitTime") * 10):
            status = await self.get_status(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                logger.error(f"模拟器{idx}启动失败，状态码: {status}")
                return False, status, {}
            if status == DeviceStatus.ONLINE:
                Ok, info = await self.get_device_info(idx)
                logger.debug(info)
                if Ok:
                    data = json.loads(info)
                    adb_port = data.get("adb_port")
                    adb_host_ip = data.get("adb_host_ip")
                    if adb_port and adb_host_ip:
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
            tuple[bool, int]: 是否成功, 当前状态码
        """
        status = await self.get_status(idx)
        if status != DeviceStatus.ONLINE and status != DeviceStatus.STARTING:
            return False, DeviceStatus.NOT_FOUND

        result = subprocess.run(
            [self.emulator_path, "control", "-v", idx, "shutdown"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        # 参考命令 MuMuManager.exe control -v 2 shutdown
        if result.returncode != 0:
            return True, DeviceStatus.OFFLINE
        for _ in range(self.config.get("Info", "MaxWaitTime") * 10):
            status = await self.get_status(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                return False, status
            if status == DeviceStatus.OFFLINE:
                return True, DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)

        return False, DeviceStatus.UNKNOWN

    async def get_status(self, idx: str, data: str | None = None) -> int:
        if not data:
            Ok, result_str = await self.get_device_info(idx)
            logger.debug(f"获取状态结果{result_str}")
        else:
            Ok, result_str = True, data

        try:
            result_json = json.loads(result_str)

            if Ok:
                if result_json["is_android_started"]:
                    return DeviceStatus.STARTING
                elif result_json["is_process_started"]:
                    return DeviceStatus.ONLINE
                else:
                    return DeviceStatus.OFFLINE

            else:
                if result_json["errmsg"] == "unknown error":
                    return DeviceStatus.UNKNOWN
                else:
                    return DeviceStatus.ERROR

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {e}")
            return DeviceStatus.UNKNOWN

    async def get_device_info(self, idx: str) -> tuple[bool, str]:
        result = subprocess.run(
            [self.emulator_path, "info", "-v", idx],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        logger.debug(f"获取模拟器{idx}信息: {result}")
        if result.returncode != 0:
            return False, result.stdout.strip()
        else:
            return True, result.stdout.strip()

    async def _get_all_info(self) -> str:
        result = subprocess.run(
            [self.emulator_path, "info", "-v", "all"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        # self.logger.debug(f"result{result.stdout.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")
        return result.stdout.strip()

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        json_data = await self._get_all_info()
        data = json.loads(json_data)

        result: dict[str, dict[str, str]] = {}

        if not data:
            return result

        if isinstance(data, dict) and "index" in data and "name" in data:
            index = data["index"]
            name = data["name"]
            status = self.get_status(index, json_data)
            result[index] = {
                "title": name,
                "status": str(status),
            }

        elif isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict) and "index" in value and "name" in value:
                    index = value["index"]
                    name = value["name"]
                    status = await self.get_status(index)
                    result[index] = {
                        "title": name,
                        "status": str(status),
                    }

        return result

    async def hide_device(self, idx: str) -> tuple[bool, int]:
        """隐藏设备窗口"""
        status = await self.get_status(idx)
        if status != DeviceStatus.ONLINE:
            return False, status
        result = subprocess.run(
            [self.emulator_path, "control", "-v", idx, "hide_window"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return False, status
        return True, DeviceStatus.ONLINE

    async def show_device(self, idx: str) -> tuple[bool, int]:
        """显示设备窗口"""
        status = await self.get_status(idx)
        if status != DeviceStatus.ONLINE:
            return False, status

        result = subprocess.run(
            [self.emulator_path, "control", "-v", idx, "show_window"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            return False, status
        return True, DeviceStatus.ONLINE
