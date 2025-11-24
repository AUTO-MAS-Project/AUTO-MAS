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
import contextlib
import win32gui
import keyboard
from datetime import datetime, timedelta
from pydantic import BaseModel
from pathlib import Path

from app.models.emulator import DeviceStatus, DeviceInfo, DeviceBase
from app.models.config import EmulatorConfig
from app.utils.logger import get_logger

logger = get_logger("雷电模拟器管理")


class LDPlayerDevice(BaseModel):
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
                f"LDPlayerManager.exe文件不存在: {config.get('Info', 'Path')}"
            )

        if config.get("Data", "Type") != "ldplayer":
            raise ValueError("配置的模拟器类型不是ldplayer")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    async def _run_cmd(self, args: list[str | Path], timeout: float | None = None):
        """以异步方式执行 dnconsole 命令，返回与 subprocess.run 类似的对象。"""
        str_args = [str(a) for a in args]
        proc = await asyncio.create_subprocess_exec(
            *str_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            raise

        # 雷电控制台输出为 GBK
        stdout = (stdout_b or b"").decode("gbk", "replace")
        stderr = (stderr_b or b"").decode("gbk", "replace")
        rc = proc.returncode if proc.returncode is not None else await proc.wait()

        class _Result:
            __slots__ = ("returncode", "stdout", "stderr")

            def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

            def __repr__(self) -> str:
                return f"Result(rc={self.returncode}, stdout={len(self.stdout)}B, stderr={len(self.stderr)}B)"

        return _Result(rc, stdout, stderr)

    async def open(self, idx: str, package_name="") -> DeviceInfo:
        logger.info(f"开始启动模拟器{idx} - {package_name}")

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
                    "launch",
                    "--index",
                    idx,
                    "--packagename",
                    f'"{package_name}"',
                ]
                if package_name
                else [self.emulator_path, "launch", "--index", idx]
            )
        )
        # 参考命令 dnconsole.exe launch --index 0

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            status = await self.getStatus(idx)
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器{idx}启动失败, 状态码: {status}")
            if status == DeviceStatus.ONLINE:
                await asyncio.sleep(3)  # 等待模拟器的 ADB 等服务完全启动
                return (await self.getInfo(idx))[idx]

            await asyncio.sleep(0.1)
        else:
            raise RuntimeError(f"模拟器{idx}启动超时, 当前状态码: {status}")

    async def close(self, idx: str) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            return status

        result = await self._run_cmd([self.emulator_path, "quit", "--index", idx])
        # 参考命令 dnconsole.exe quit --index 0

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

    async def getStatus(
        self, idx: str, data: LDPlayerDevice | None = None
    ) -> DeviceStatus:
        if data is None:
            try:
                data = (await self.get_device_info(idx))[idx]
            except Exception as e:
                logger.error(f"获取模拟器{idx}信息失败: {e}")
                return DeviceStatus.ERROR

        # 计算状态码
        if data.in_android == 1:
            return DeviceStatus.ONLINE
        elif data.in_android == 2:
            if data.vbox_pid > 0:
                return DeviceStatus.STARTING
                # 雷电启动后, vbox_pid为-1, 目前不知道有什么区别
            else:
                return DeviceStatus.STARTING
        elif data.in_android == 0:
            return DeviceStatus.OFFLINE
        else:
            return DeviceStatus.UNKNOWN

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        data = await self.get_device_info(idx)
        result: dict[str, DeviceInfo] = {}

        for idx, info in data.items():
            status = await self.getStatus(idx, info)
            adb_port = f"127.0.0.1:{await self.get_adb_ports(info.vbox_pid)}"
            result[idx] = DeviceInfo(
                title=info.title, status=status, adb_address=adb_port
            )

        return result

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        result = (await self.get_device_info(idx))[idx]

        t = datetime.now()
        while datetime.now() - t < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            # 检查窗口可见性是否符合预期
            if win32gui.IsWindowVisible(result.top_hwnd) == is_visible:
                return status

            try:
                keyboard.press_and_release(
                    "+".join(
                        _.strip().lower()
                        for _ in json.loads(self.config.get("Info", "BossKeys"))
                    )
                )  # 老板键
            except Exception as e:
                logger.error(f"发送BOSS键失败: {e}")

            await asyncio.sleep(0.5)

        else:
            raise RuntimeError(f"隐藏设备{idx}窗口超时")

    async def get_device_info(self, idx: str | None) -> dict[str, LDPlayerDevice]:
        """获取模拟器的信息"""

        result = await self._run_cmd([self.emulator_path, "list2"])

        # logger.debug(f"全部信息{result.stdout.strip()}")
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result}")

        emulators: dict[str, LDPlayerDevice] = {}
        data = result.stdout.strip()

        for line in data.strip().splitlines():
            parts = line.strip().split(",")
            if len(parts) != 10:
                raise ValueError(f"数据格式错误: {line}")
            if idx is not None and parts[0] != idx:
                continue
            try:
                emulators[parts[0]] = LDPlayerDevice(
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
            except Exception as e:
                logger.warning(f"解析失败: {line}, 错误: {e}")

        if idx is not None and len(emulators) == 0:
            raise RuntimeError("未找到对应模拟器信息")

        return emulators

    # ?wk雷电你都返回了什么啊

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
