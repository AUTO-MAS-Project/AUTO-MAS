import asyncio
import json
from app.core.emulator_manager.utils import BaseDevice, ExeRunner, DeviceStatus
from app.utils.logger import get_logger
from app.models.config import EmulatorManagerConfig


class MumuManager(BaseDevice):
    """
    基于MuMuManager.exe的模拟器管理
    """

    def __init__(self, config: EmulatorManagerConfig) -> None:
        """_summary_

        Args:
            exe_path (str): MuMuManager.exe的绝对路径
        """
        super().__init__(config)
        self.runner = ExeRunner(
            config.get("Info", "ExePath"),
            "utf-8",
        )
        self.logger = get_logger("MuMu管理器")

    async def start(self, idx: str, package_name="") -> tuple[bool, int, dict]:
        """
        启动指定模拟器
        Returns:
            tuple[bool, int, str]: 是否成功, 当前状态码, ADB端口信息
        """
        status = await self.get_status(idx)
        if status != DeviceStatus.OFFLINE:
            self.logger.error(
                f"模拟器{idx}未处于关闭状态，当前状态码: {status}, 需求状态码: {DeviceStatus.OFFLINE}"
            )
            return False, status, {}
        if package_name:
            result = self.runner.run(
                "control",
                "-v",
                idx,
                "launch",
                "-pkg",
                package_name,
            )
        else:
            result = self.runner.run(
                "control",
                "-v",
                idx,
                "launch",
            )
        # 参考命令 MuMuManager.exe control -v 2 launch
        self.logger.debug(f"启动结果:{result}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        i = 0
        while i < self.max_wait_time * 10:
            status = await self.get_status(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                self.logger.error(f"模拟器{idx}启动失败，状态码: {status}")
                return False, status, {}
            if status == DeviceStatus.ONLINE:
                OK, info = await self.get_device_info(idx)
                self.logger.debug(info)
                if OK:
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
            i += 1
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
        result = self.runner.run(
            "control",
            "-v",
            idx,
            "shutdown",
        )
        # 参考命令 MuMuManager.exe control -v 2 shutdown
        if result.returncode != 0:
            return True, DeviceStatus.OFFLINE
        i = 0
        while i < self.max_wait_time * 10:
            status = await self.get_status(idx)
            if status == DeviceStatus.ERROR or status == DeviceStatus.UNKNOWN:
                return False, status
            if status == DeviceStatus.OFFLINE:
                return True, DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)
            i += 1

        return False, DeviceStatus.UNKNOWN

    async def get_status(self, idx: str, data: str | None = None) -> int:
        if not data:
            OK, result_str = await self.get_device_info(idx)
            self.logger.debug(f"获取状态结果{result_str}")
        else:
            OK, result_str = True, data

        try:
            result_json = json.loads(result_str)

            if OK:
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
            self.logger.error(f"JSON解析错误: {e}")
            return DeviceStatus.UNKNOWN

    async def get_device_info(self, idx: str) -> tuple[bool, str]:
        result = self.runner.run(
            "info",
            "-v",
            idx,
        )
        self.logger.debug(f"获取模拟器{idx}信息: {result}")
        if result.returncode != 0:
            return False, result.stdout.strip()
        else:
            return True, result.stdout.strip()

    async def _get_all_info(self) -> str:
        result = self.runner.run(
            "info",
            "-v",
            "all",
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
        result = self.runner.run(
            "control",
            "-v",
            idx,
            "hide_window",
        )
        if result.returncode != 0:
            return False, status
        return True, DeviceStatus.ONLINE

    async def show_device(self, idx: str) -> tuple[bool, int]:
        """显示设备窗口"""
        status = await self.get_status(idx)
        if status != DeviceStatus.ONLINE:
            return False, status
        result = self.runner.run(
            "control",
            "-v",
            idx,
            "show_window",
        )
        if result.returncode != 0:
            return False, status
        return True, DeviceStatus.ONLINE
