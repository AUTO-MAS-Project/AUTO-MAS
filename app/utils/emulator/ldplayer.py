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


import json
import psutil
import asyncio

from app.utils.platform import IS_WINDOWS

if IS_WINDOWS:
    import win32gui
    import keyboard
from datetime import datetime, timedelta
import time
from pydantic import BaseModel
from pathlib import Path

from app.models.emulator import DeviceStatus, DeviceInfo, DeviceBase
from app.models.config import EmulatorConfig
from app.utils import ProcessRunner, get_logger

logger = get_logger("雷电模拟器管理")

_CONFIG_GUARD_DELAY_SECONDS = 3.0
_INSTANCE_LOCKS: dict[tuple[asyncio.AbstractEventLoop, str, str], asyncio.Lock] = {}
_INSTANCE_CONFIG_SNAPSHOTS: dict[tuple[str, str], bytes] = {}


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

        if config.get("Info", "Type") != "ldplayer":
            raise ValueError("配置的模拟器类型不是ldplayer")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    def _get_instance_key(self, idx: str) -> tuple[str, str]:
        return str(self.emulator_path.resolve()).casefold(), str(idx)

    def _get_instance_lock(self, idx: str) -> asyncio.Lock:
        instance_key = self._get_instance_key(idx)
        lock_key = (asyncio.get_running_loop(), *instance_key)
        return _INSTANCE_LOCKS.setdefault(lock_key, asyncio.Lock())

    def _get_instance_config_path(self, idx: str) -> Path | None:
        idx_text = str(idx)
        if not idx_text.isdecimal():
            logger.warning(f"无法保护雷电模拟器配置，实例索引无效: {idx}")
            return None
        return (
            self.emulator_path.parent / "vms" / "config" / f"leidian{idx_text}.config"
        )

    @staticmethod
    def _is_config_guard_enabled() -> bool:
        try:
            from app.core import Config

            return bool(Config.get("Function", "IfBlockAd"))
        except Exception as e:
            logger.warning(f"读取雷电模拟器配置保护开关失败: {e}")
            return False

    async def _capture_instance_config(self, idx: str) -> None:
        instance_key = self._get_instance_key(idx)
        if not self._is_config_guard_enabled():
            _INSTANCE_CONFIG_SNAPSHOTS.pop(instance_key, None)
            return

        if instance_key in _INSTANCE_CONFIG_SNAPSHOTS:
            return

        config_path = self._get_instance_config_path(idx)
        if config_path is None:
            return

        try:
            snapshot = await asyncio.to_thread(config_path.read_bytes)
        except Exception as e:
            logger.warning(f"读取雷电模拟器 {idx} 配置快照失败: {e}")
            return

        _INSTANCE_CONFIG_SNAPSHOTS[instance_key] = snapshot
        logger.info(f"已保存雷电模拟器 {idx} 启动前配置快照")

    async def _verify_and_restore_instance_config(self, idx: str) -> None:
        instance_key = self._get_instance_key(idx)
        snapshot = _INSTANCE_CONFIG_SNAPSHOTS.get(instance_key)
        if snapshot is None:
            return

        if not self._is_config_guard_enabled():
            _INSTANCE_CONFIG_SNAPSHOTS.pop(instance_key, None)
            return

        logger.info(
            f"雷电模拟器 {idx} 已关闭，等待 "
            f"{_CONFIG_GUARD_DELAY_SECONDS:g} 秒后校验配置"
        )
        await asyncio.sleep(_CONFIG_GUARD_DELAY_SECONDS)

        config_path = self._get_instance_config_path(idx)
        if config_path is None:
            return

        try:
            current = await asyncio.to_thread(config_path.read_bytes)
        except FileNotFoundError:
            logger.warning(f"关闭后未找到雷电模拟器 {idx} 配置，将尝试恢复快照")
            current = None
        except Exception as e:
            logger.warning(f"校验雷电模拟器 {idx} 配置失败: {e}")
            return

        if current == snapshot:
            _INSTANCE_CONFIG_SNAPSHOTS.pop(instance_key, None)
            logger.info(f"雷电模拟器 {idx} 配置校验通过")
            return

        try:
            await asyncio.to_thread(config_path.write_bytes, snapshot)
        except Exception as e:
            logger.warning(f"恢复雷电模拟器 {idx} 配置失败: {e}")
            return

        _INSTANCE_CONFIG_SNAPSHOTS.pop(instance_key, None)
        logger.warning(f"雷电模拟器 {idx} 配置发生变化，已恢复启动前快照")

    async def open(self, idx: str, package_name="") -> DeviceInfo:
        async with self._get_instance_lock(idx):
            return await self._open_locked(idx, package_name)

    async def _open_locked(self, idx: str, package_name: str) -> DeviceInfo:
        logger.info(f"开始启动模拟器 {idx}  - {package_name}")

        status = DeviceStatus.UNKNOWN  # 初始化status变量
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if status == DeviceStatus.ONLINE:
                return (await self.getInfo(idx))[idx]
            elif status == DeviceStatus.OFFLINE:
                break
            await asyncio.sleep(0.1)

        else:
            raise RuntimeError(f"模拟器 {idx} 无法启动, 当前状态码: {status}")

        await self._capture_instance_config(idx)

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "launch",
            "--index",
            idx,
            *(["--packagename", f'"{package_name}"'] if package_name else []),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        # 参考命令 dnconsole.exe launch --index 0

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")

        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if status == DeviceStatus.ONLINE:
                await asyncio.sleep(
                    30
                    if package_name != ""
                    and self.config.get("Info", "MaxWaitTime") > 60
                    else 3
                )  # 等待模拟器的 ADB 等服务完全启动, 低性能设备额外等待应用启动
                from app.core import Config

                if Config.get("Function", "IfBlockAd"):
                    await self._block_ads_via_adb(idx)
                return (await self.getInfo(idx))[idx]

            await asyncio.sleep(0.1)
        else:
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器 {idx} 启动失败, 状态码: {status}")
            raise RuntimeError(f"模拟器 {idx} 启动超时, 当前状态码: {status}")

    async def close(self, idx: str) -> DeviceStatus:
        async with self._get_instance_lock(idx):
            return await self._close_locked(idx)

    async def _close_locked(self, idx: str) -> DeviceStatus:
        status = await self.getStatus(idx)
        if status not in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
            logger.warning(f"设备{idx}未在线，当前状态: {status}")
            if status == DeviceStatus.OFFLINE:
                await self._verify_and_restore_instance_config(idx)
            return status

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "quit",
            "--index",
            idx,
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        # 参考命令 dnconsole.exe quit --index 0

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if status == DeviceStatus.OFFLINE:
                await self._verify_and_restore_instance_config(idx)
                return DeviceStatus.OFFLINE
            await asyncio.sleep(0.1)

        else:
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器 {idx} 关闭失败, 状态码: {status}")
            raise RuntimeError(f"模拟器 {idx} 关闭超时, 当前状态码: {status}")

    async def getStatus(
        self, idx: str, data: LDPlayerDevice | None = None
    ) -> DeviceStatus:
        if data is None:
            try:
                data = (await self.get_device_info(idx))[idx]
            except Exception as e:
                logger.error(f"获取模拟器 {idx} 信息失败: {e}")
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
            adb_port = await self.get_adb_ports(info.vbox_pid)
            result[idx] = DeviceInfo(
                title=info.title,
                status=status,
                adb_address=(
                    f"127.0.0.1:{adb_port}"
                    if adb_port != 0
                    else f"emulator-{5554 + int(idx) * 2}"
                ),
            )

        return result

    async def list_devices(self) -> dict[str, str]:
        data = await self.get_device_info(None)
        return {idx: info.title for idx, info in data.items()}

    async def setVisible(self, idx: str, is_visible: bool) -> DeviceStatus:
        if not IS_WINDOWS:
            raise RuntimeError("切换模拟器窗口可见性仅支持 Windows 平台")

        status = await self.getStatus(idx)
        if status != DeviceStatus.ONLINE:
            logger.warning(f"设备{idx}未在线，当前状态码: {status}")
            return status

        result = (await self.get_device_info(idx))[idx]

        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            # 检查窗口可见性是否符合预期
            if win32gui.IsWindowVisible(result.top_hwnd) == is_visible:
                return status

            try:
                keyboard.press_and_release(
                    "+".join(
                        _.strip().lower()
                        for _ in json.loads(self.config.get("Info", "BossKey"))
                    )
                )  # 老板键
            except Exception as e:
                logger.error(f"发送BOSS键失败: {e}")

            await asyncio.sleep(0.5)

        else:
            raise RuntimeError(f"隐藏设备{idx}窗口超时")

    async def get_device_info(self, idx: str | None) -> dict[str, LDPlayerDevice]:
        """获取模拟器的信息"""

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "list2",
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")
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

    def get_adb_path(self) -> Path | None:
        adb_path = self.emulator_path.parent / "adb.exe"
        return adb_path if adb_path.exists() else None

    async def _block_ads_via_adb(self, idx: str) -> None:
        adb_path = self.emulator_path.parent / "adb.exe"
        adb_serial = f"emulator-{5554 + int(idx) * 2}"  # 雷电模拟器 ADB 设备名固定格式

        for package in ["com.android.flysilkworm"]:
            result = await ProcessRunner.run_process(
                adb_path,
                "-s",
                adb_serial,
                "shell",
                "pm",
                "disable-user",
                "--user",
                "0",
                package,
                timeout=10,
            )
            if result.returncode == 0:
                logger.success(f"已禁用广告包: {package}")
            else:
                logger.warning(
                    f"禁用广告包 {package} 失败, returncode={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
                )

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
