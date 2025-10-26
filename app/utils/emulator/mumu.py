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
import contextlib
from datetime import datetime, timedelta
from pathlib import Path


from app.models.emulator import DeviceStatus, DeviceInfo, DeviceBase
from app.models.config import EmulatorConfig
from app.utils.logger import get_logger


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

    async def _run_cmd(self, args: list[str | Path], timeout: float | None = None):
        """以异步方式执行 MuMuManager 命令，返回与 subprocess.run 类似的对象。

        - 不使用 shell，避免注入风险。
        - 接受 Path 或 str 参数；输出按 utf-8 + replace 解码，保持与原实现一致。
        - 可选超时：超时将终止子进程并抛出 asyncio.TimeoutError。
        """
        # 将 Path/其他可路径对象转为字符串
        str_args = [str(a) for a in args]

        proc = await asyncio.create_subprocess_exec(
            *str_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # NOTE: 默认不设超时，由上层逻辑通过 MaxWaitTime 进行整体控制；此处保留 timeout 以便未来扩展。
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            raise

        stdout = (stdout_b or b"").decode("utf-8", "replace")
        stderr = (stderr_b or b"").decode("utf-8", "replace")
        rc = proc.returncode if proc.returncode is not None else await proc.wait()

        class _Result:
            __slots__ = ("returncode", "stdout", "stderr")

            def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

            def __repr__(self) -> str:  # 便于日志显示
                return f"Result(rc={self.returncode}, stdout={len(self.stdout)}B, stderr={len(self.stderr)}B)"

        return _Result(rc, stdout, stderr)

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        logger.info(f"开始启动模拟器{idx} - {package_name}")

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
            raise RuntimeError(f"模拟器{idx}无法启动, 当前状态码: {status}")

        result = await self._run_cmd(
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
            )
        )
        # 参考命令 MuMuManager.exe control -v 2 launch

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器{idx}启动失败, 状态码: {status}")
            elif (
                Config.get("Function", "IfSilence") and status == DeviceStatus.STARTING
            ):
                await self.setVisible(idx, False)
            elif status == DeviceStatus.ONLINE:
                return (await self.getInfo(idx))[idx]
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"模拟器{idx}启动超时, 当前状态码: {status}")

    async def close(self, idx: str) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            return status

        result = await self._run_cmd(
            [
                self.emulator_path,
                "control",
                "-v",
                idx,
                "shutdown",
            ]
        )
        # 参考命令 MuMuManager.exe control -v 2 shutdown

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器{idx}关闭失败, 状态码: {status}")
            if status == DeviceStatus.OFFLINE:
                return DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)

        else:
            raise RuntimeError(f"模拟器{idx}关闭超时, 当前状态码: {status}")

    async def getStatus(self, idx: str, data: str | None = None) -> DeviceStatus:
        if data is None:
            try:
                data = await self.get_device_info(idx)
            except Exception as e:
                logger.error(f"获取模拟器{idx}信息失败: {e}")
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

        result = await self._run_cmd(
            [
                self.emulator_path,
                "control",
                "-v",
                idx,
                "show_window" if is_visible else "hide_window",
            ]
        )
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        return await self.getStatus(idx)

    async def get_device_info(self, idx: str) -> str:
        result = await self._run_cmd([self.emulator_path, "info", "-v", idx])
        if result.returncode != 0:
            logger.error(f"获取模拟器{idx}信息失败: {result.stdout.strip()}")
            raise RuntimeError(f"命令执行失败: {result}")

        return result.stdout.strip()
