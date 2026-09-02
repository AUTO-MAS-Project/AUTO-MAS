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
    import win32con
    import win32process
from contextlib import suppress
from datetime import datetime, timedelta
import time
from pathlib import Path

from app.models.emulator import DeviceStatus, DeviceInfo, DeviceBase
from app.models.config import EmulatorConfig
from app.utils import ProcessRunner, get_logger


logger = get_logger("MuMu模拟器管理")

MUMU_FORCE_KILL_KEYWORDS = (
    "mumunxdevice",
    "mumunxmain",
    "mumuvmmheadless",
)
MUMU_STORE_PACKAGE = "com.mumu.store"
MUMU_STORE_OVERLAY_APP_OP = "SYSTEM_ALERT_WINDOW"


class MumuManager(DeviceBase):
    """
    基于MuMuManager.exe的模拟器管理
    """

    def __init__(self, config: EmulatorConfig) -> None:
        if not (Path(config.get("Info", "Path"))).exists():
            raise FileNotFoundError(
                f"MuMuManager.exe文件不存在: {config.get('Info', 'Path')}"
            )

        if config.get("Info", "Type") != "mumu":
            raise ValueError("配置的模拟器类型不是mumu")

        self.config = config

        self.emulator_path = Path(config.get("Info", "Path"))

    def get_adb_path(self) -> Path | None:
        adb_path = self.emulator_path.parent / "adb.exe"
        return adb_path if adb_path.exists() else None

    async def _get_app_state(self, idx: str, package_name: str) -> str | None:
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "control",
                "-v",
                idx,
                "app",
                "info",
                "-pkg",
                package_name,
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(f"获取 MuMu 应用状态失败: {e}")
            return None

        if result.returncode != 0:
            logger.warning(f"获取 MuMu 应用状态失败: {result.stdout.strip()}")
            return None

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            logger.warning(f"解析 MuMu 应用状态失败: {e}")
            return None

        if not isinstance(data, dict) or not isinstance(data.get("state"), str):
            logger.warning(f"MuMu 应用状态返回异常: {result.stdout.strip()}")
            return None

        return data["state"].strip().lower()

    @staticmethod
    def _is_app_foreground(data: str, package_name: str) -> bool:
        package_component = f"{package_name}/"
        foreground_markers = (
            "topResumedActivity=",
            "ResumedActivity:",
            "mResumedActivity:",
            "mCurrentFocus=",
        )
        return any(
            package_component in line
            and any(marker in line for marker in foreground_markers)
            for line in data.splitlines()
        )

    async def _wait_app_foreground(self, idx: str, package_name: str) -> bool:
        for attempt in range(6):
            try:
                result = await ProcessRunner.run_process(
                    self.emulator_path,
                    "adb",
                    "-v",
                    idx,
                    "shell",
                    "dumpsys",
                    "activity",
                    "activities",
                    timeout=self.config.get("Info", "MaxWaitTime"),
                    if_merge_std=True,
                    breakaway=True,
                )
            except Exception as e:
                logger.debug(f"检查 MuMu 应用前台状态失败: {e}")
            else:
                if result.returncode == 0 and self._is_app_foreground(
                    result.stdout, package_name
                ):
                    return True
                if result.returncode != 0:
                    logger.debug(f"检查 MuMu 应用前台状态失败: {result.stdout.strip()}")

            if attempt < 5:
                await asyncio.sleep(1)

        return False

    async def _ensure_app_foreground(self, idx: str, package_name: str) -> bool:
        state = await self._get_app_state(idx, package_name)
        if state != "running":
            try:
                result = await ProcessRunner.run_process(
                    self.emulator_path,
                    "control",
                    "-v",
                    idx,
                    "app",
                    "launch",
                    "-pkg",
                    package_name,
                    timeout=self.config.get("Info", "MaxWaitTime"),
                    if_merge_std=True,
                    breakaway=True,
                )
                if result.returncode != 0:
                    logger.warning(f"MuMu 应用补启动失败: {result.stdout.strip()}")
            except Exception as e:
                logger.warning(f"MuMu 应用补启动失败: {e}")

        if await self._wait_app_foreground(idx, package_name):
            return True

        logger.warning(f"MuMu 应用未进入前台，尝试使用 monkey 补启动: {package_name}")
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "monkey",
                "-p",
                package_name,
                "1",
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
            if result.returncode != 0:
                logger.warning(f"MuMu monkey 补启动失败: {result.stdout.strip()}")
        except Exception as e:
            logger.warning(f"MuMu monkey 补启动失败: {e}")

        if await self._wait_app_foreground(idx, package_name):
            return True

        logger.warning(
            f"MuMu 应用补启动后仍未进入前台，将继续运行: {idx} - {package_name}"
        )
        return False

    async def _block_store_overlay_ads(self, idx: str) -> None:
        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "appops",
                "set",
                MUMU_STORE_PACKAGE,
                MUMU_STORE_OVERLAY_APP_OP,
                "deny",
                timeout=10,
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(f"屏蔽 MuMu 应用商店悬浮广告失败: {e}")
        else:
            if result.returncode == 0:
                logger.success("已屏蔽 MuMu 应用商店悬浮广告")
            else:
                logger.warning(
                    f"屏蔽 MuMu 应用商店悬浮广告失败: {result.stdout.strip()}"
                )

        try:
            result = await ProcessRunner.run_process(
                self.emulator_path,
                "adb",
                "-v",
                idx,
                "shell",
                "am",
                "force-stop",
                MUMU_STORE_PACKAGE,
                timeout=10,
                if_merge_std=True,
                breakaway=True,
            )
        except Exception as e:
            logger.warning(f"停止 MuMu 应用商店广告进程失败: {e}")
            return

        if result.returncode == 0:
            logger.success("已停止 MuMu 应用商店广告进程")
        else:
            logger.warning(f"停止 MuMu 应用商店广告进程失败: {result.stdout.strip()}")

    async def open(self, idx: str, package_name: str = "") -> DeviceInfo:
        logger.info(f"开始启动模拟器 {idx}  - {package_name}")

        from app.core import Config

        status = DeviceStatus.UNKNOWN  # 初始化status变量
        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if status == DeviceStatus.ONLINE:
                if Config.get("Function", "IfBlockAd"):
                    await self._block_store_overlay_ads(idx)
                return (await self.getInfo(idx))[idx]
            elif status == DeviceStatus.OFFLINE:
                break
            await asyncio.sleep(0.1)

        else:
            raise RuntimeError(f"模拟器 {idx} 无法启动, 当前状态码: {status}")

        if_close_mumu_nx = await self.find_mumu_nx_window() is None

        # 启动实例前关闭 MuMu 应用保活
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "setting",
            "-v",
            idx,
            "-k",
            "app_keptlive",
            "-val",
            "false",
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"设置 app_keptlive 失败: {result.stdout}")

        result = await ProcessRunner.run_process(
            self.emulator_path,
            "control",
            "-v",
            idx,
            "launch",
            *(["-pkg", package_name] if package_name else []),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        # 参考命令 MuMuManager.exe control -v 2 launch

        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout}")

        deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
        while time.monotonic() < deadline:
            status = await self.getStatus(idx)
            if if_close_mumu_nx:
                if_close_mumu_nx = not await self.close_mumu_nx_window()
            if Config.get("Function", "IfSilence") and status == DeviceStatus.STARTING:
                await self.setVisible(idx, False)
            elif status == DeviceStatus.ONLINE:
                if Config.get("Function", "IfBlockAd"):
                    await self._block_store_overlay_ads(idx)
                if package_name:
                    try:
                        await self._ensure_app_foreground(idx, package_name)
                    except Exception as e:
                        logger.warning(
                            f"MuMu 应用检查或补启动异常，将继续运行: "
                            f"{idx} - {package_name} - {e}"
                        )
                    await asyncio.sleep(
                        30 if self.config.get("Info", "MaxWaitTime") > 60 else 3
                    )
                else:
                    await asyncio.sleep(3)
                return (await self.getInfo(idx))[idx]
            await asyncio.sleep(0.1)
        else:
            if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                raise RuntimeError(f"模拟器 {idx} 启动失败, 状态码: {status}")
            raise RuntimeError(f"模拟器 {idx} 启动超时, 当前状态码: {status}")

    async def close(self, idx: str) -> DeviceStatus:
        try:
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
                timeout=self.config.get("Info", "MaxWaitTime"),
                if_merge_std=True,
                breakaway=True,
            )
            # 参考命令 MuMuManager.exe control -v 2 shutdown

            if result.returncode != 0:
                raise RuntimeError(f"命令执行失败: {result.stdout}")

            deadline = time.monotonic() + self.config.get("Info", "MaxWaitTime")
            while time.monotonic() < deadline:
                status = await self.getStatus(idx)
                if status == DeviceStatus.OFFLINE:
                    return DeviceStatus.OFFLINE
                await asyncio.sleep(0.1)

            else:
                if status in [DeviceStatus.ERROR, DeviceStatus.UNKNOWN]:
                    raise RuntimeError(f"模拟器 {idx} 关闭失败, 状态码: {status}")
                raise RuntimeError(f"模拟器 {idx} 关闭超时, 当前状态码: {status}")
        finally:
            if self.config.get("Info", "ForceKillOnClose"):
                self._force_kill_mumu_processes()

    def _force_kill_mumu_processes(self) -> None:
        """按 MuMu 固定进程白名单清理关闭后的残留进程。"""

        killed_count = 0
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                proc_name = proc.info.get("name") or ""
                proc_exe = proc.info.get("exe") or ""
                if not self._is_mumu_force_kill_target(proc_name, proc_exe):
                    continue

                killed_count += self._kill_process_tree(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError) as e:
                logger.warning(f"强力清理 MuMu 残留进程失败: {e}")

        if killed_count > 0:
            logger.info(f"MuMu 残留进程清理完成，共结束 {killed_count} 个进程")
        else:
            logger.info("未发现需要强力清理的 MuMu 残留进程")

    def _kill_process_tree(self, proc: psutil.Process) -> int:
        killed_count = 0
        for child in proc.children(recursive=True):
            killed_count += self._kill_process(child)
        killed_count += self._kill_process(proc)
        return killed_count

    @staticmethod
    def _kill_process(proc: psutil.Process) -> int:
        try:
            proc.kill()
            return 1
        except psutil.NoSuchProcess:
            return 0
        except (psutil.AccessDenied, OSError) as e:
            logger.warning(f"强力清理 MuMu 残留进程失败: {e}")
            return 0

    @staticmethod
    def _is_mumu_force_kill_target(proc_name: str, proc_exe: str) -> bool:
        target_text = f"{proc_name} {proc_exe}".lower()
        return any(keyword in target_text for keyword in MUMU_FORCE_KILL_KEYWORDS)

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

        return self._get_status_from_data(data_json)

    @staticmethod
    def _get_status_from_data(data: dict[str, object]) -> DeviceStatus:
        if data["is_android_started"]:
            return DeviceStatus.ONLINE
        elif data["is_process_started"]:
            return DeviceStatus.STARTING
        else:
            return DeviceStatus.OFFLINE

    @staticmethod
    def _resolve_adb_address(data: dict[str, object]) -> str | None:
        host = data.get("adb_host_ip") or data.get("adb_host")
        port = data.get("adb_port")
        if host and port:
            return f"{host}:{port}"

        return None

    @staticmethod
    def _get_default_adb_address(index: str | int) -> str:
        try:
            return f"127.0.0.1:{5555 + int(index) * 2}"
        except (TypeError, ValueError):
            return "Unknown"

    @staticmethod
    def _extract_device_entries(data: object) -> list[dict[str, object]]:
        if not isinstance(data, dict):
            return []

        if "index" in data and "name" in data:
            return [data]

        return [
            value
            for value in data.values()
            if isinstance(value, dict) and "index" in value and "name" in value
        ]

    async def _get_adb_address(self, data: dict[str, object], index: str | int) -> str:
        adb_address = self._resolve_adb_address(data)
        if adb_address is not None:
            return adb_address

        try:
            adb_data = await self.get_adb_info(index)
            adb_json = json.loads(adb_data)
        except Exception as e:
            logger.debug(
                f"获取 MuMu 模拟器 {index} ADB 信息失败，使用默认端口兜底: {e}"
            )
        else:
            if isinstance(adb_json, dict):
                adb_address = self._resolve_adb_address(adb_json)
                if adb_address is not None:
                    return adb_address
            logger.debug(
                f"MuMu 模拟器 {index} ADB 信息缺少 host/port，使用默认端口兜底"
            )

        return self._get_default_adb_address(index)

    async def getInfo(self, idx: str | None) -> dict[str, DeviceInfo]:
        data = await self.get_device_info(idx or "all")

        data_json = json.loads(data)

        result: dict[str, DeviceInfo] = {}

        for value in self._extract_device_entries(data_json):
            index = str(value["index"])
            name = value["name"]
            status = self._get_status_from_data(value)
            adb_address = await self._get_adb_address(value, index)
            result[index] = DeviceInfo(
                title=name, status=status, adb_address=adb_address
            )

        return result

    async def list_devices(self) -> dict[str, str]:
        data_json = json.loads(await self.get_device_info("all"))

        return {
            str(value["index"]): str(value["name"])
            for value in self._extract_device_entries(data_json)
        }

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
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
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
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            logger.error(f"获取模拟器 {idx} 信息失败: {result.stdout.strip()}")
            raise RuntimeError(f"命令执行失败: {result.stdout.strip()}")

        return result.stdout.strip()

    async def get_adb_info(self, idx: str | int) -> str:
        result = await ProcessRunner.run_process(
            self.emulator_path,
            "adb",
            "-v",
            str(idx),
            timeout=self.config.get("Info", "MaxWaitTime"),
            if_merge_std=True,
            breakaway=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {result.stdout.strip()}")

        return result.stdout.strip()

    async def find_mumu_nx_window(self) -> int | None:
        """
        查找 MuMu 多开器窗口

        Returns:
            int | None: 窗口句柄，未找到返回 None
        """

        if not IS_WINDOWS:
            return None

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
