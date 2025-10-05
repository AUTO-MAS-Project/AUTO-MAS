#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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

#!其实压根用不了
import asyncio
import psutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any
from app.core.emulator_manager.utils import BaseDevice, DeviceStatus
from app.utils.logger import get_logger


class ProcessManager:
    """进程监视器类, 用于跟踪主进程及其所有子进程的状态"""

    def __init__(self):
        super().__init__()

        self.main_pid = None
        self.tracked_pids = set()
        self.check_task = None
        self.track_end_time = datetime.now()

    async def open_process(
        self, path: Path, args: list = [], tracking_time: int = 60
    ) -> None:
        """
        启动一个新进程并返回其pid, 并开始监视该进程

        Parameters
        ----------
        path: 可执行文件的路径
        args: 启动参数列表
        tracking_time: 子进程追踪持续时间（秒）
        """

        process = subprocess.Popen(
            [path, *args],
            cwd=path.parent,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        await self.start_monitoring(process.pid, tracking_time)

    async def start_monitoring(self, pid: int, tracking_time: int = 60) -> None:
        """
        启动进程监视器, 跟踪指定的主进程及其子进程

        :param pid: 被监视进程的PID
        :param tracking_time: 子进程追踪持续时间（秒）
        """

        await self.clear()

        self.main_pid = pid
        self.tracking_time = tracking_time

        # 扫描并记录所有相关进程
        try:
            # 获取主进程
            main_proc = psutil.Process(self.main_pid)
            self.tracked_pids.add(self.main_pid)

            # 递归获取所有子进程
            if tracking_time:
                for child in main_proc.children(recursive=True):
                    self.tracked_pids.add(child.pid)

        except psutil.NoSuchProcess:
            pass

        # 启动持续追踪任务
        if tracking_time > 0:
            self.track_end_time = datetime.now() + timedelta(seconds=tracking_time)
            self.check_task = asyncio.create_task(self.track_processes())

    async def track_processes(self) -> None:
        """更新子进程列表"""

        while datetime.now() < self.track_end_time:
            current_pids = set(self.tracked_pids)
            for pid in current_pids:
                try:
                    proc = psutil.Process(pid)
                    for child in proc.children():
                        if child.pid not in self.tracked_pids:
                            # 新发现的子进程
                            self.tracked_pids.add(child.pid)
                except psutil.NoSuchProcess:
                    continue
            await asyncio.sleep(0.1)

    async def is_running(self) -> bool:
        """检查所有跟踪的进程是否还在运行"""

        for pid in self.tracked_pids:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    return True
            except psutil.NoSuchProcess:
                continue

        return False

    async def kill(self, if_force: bool = False) -> None:
        """停止监视器并中止所有跟踪的进程"""

        for pid in self.tracked_pids:
            try:
                proc = psutil.Process(pid)
                if if_force:
                    kill_process = subprocess.Popen(
                        ["taskkill", "/F", "/T", "/PID", str(pid)],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    kill_process.wait()
                proc.terminate()
            except psutil.NoSuchProcess:
                continue

        await self.clear()

    async def clear(self) -> None:
        """清空跟踪的进程列表"""

        if self.check_task is not None and not self.check_task.done():
            self.check_task.cancel()

            try:
                await self.check_task
            except asyncio.CancelledError:
                pass

        self.main_pid = None
        self.tracked_pids.clear()


class GeneralDeviceManager(BaseDevice):
    """
    通用设备管理器，基于BaseDevice和ProcessManager实现
    用于管理一般应用程序进程
    """

    def __init__(self, config_instance):
        """
        初始化通用设备管理器

        Args:
            executable_path (str): 可执行文件的绝对路径
            name (str): 设备管理器名称
        """
        self.executable_path = Path(config_instance.get("Info", "ExePath"))
        self.name = config_instance.get("Info", "Name")
        self.logger = get_logger(f"{self.name}管理器")

        # 进程管理实例字典，以idx为键
        self.process_managers: Dict[str, ProcessManager] = {}

        # 设备信息存储
        self.device_info: Dict[str, Dict[str, Any]] = {}

        # 默认等待时间
        self.wait_time = 60

        if not self.executable_path.exists():
            raise FileNotFoundError(
                f"可执行文件不存在: {config_instance.get("Info", "ExePath")}"
            )

    async def start(self, idx: str, package_name: str = "") -> tuple[bool, int, dict]:
        """
        启动设备

        Args:
            idx: 设备ID
            package_name: 包名（可选）

        Returns:
            tuple[bool, int, dict]: (是否成功, 状态码, 启动信息)
        """
        try:
            # 检查是否已经在运行
            current_status = await self.get_status(idx)
            if current_status in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
                self.logger.warning(f"设备{idx}已经在运行，状态: {current_status}")
                return False, current_status, {}

            # 创建进程管理器
            if idx not in self.process_managers:
                self.process_managers[idx] = ProcessManager()

            # 准备启动参数
            args = []
            if package_name:
                args.extend(["-pkg", package_name])

            # 启动进程
            await self.process_managers[idx].open_process(
                self.executable_path, args, tracking_time=self.wait_time
            )

            # 等待进程启动
            start_time = datetime.now()
            timeout = timedelta(seconds=self.wait_time)

            while datetime.now() - start_time < timeout:
                if await self.process_managers[idx].is_running():
                    self.device_info[idx] = {
                        "title": f"{self.name}_{idx}",
                        "status": str(DeviceStatus.ONLINE),
                        "pid": self.process_managers[idx].main_pid,
                        "start_time": start_time.isoformat(),
                    }

                    self.logger.info(f"设备{idx}启动成功")
                    return True, DeviceStatus.ONLINE, self.device_info[idx]

                await asyncio.sleep(0.1)

            self.logger.error(f"设备{idx}启动超时")
            return False, DeviceStatus.ERROR, {}

        except Exception as e:
            self.logger.error(f"启动设备{idx}失败: {str(e)}")
            return False, DeviceStatus.ERROR, {}

    async def close(self, idx: str) -> tuple[bool, int]:
        """
        关闭设备或服务

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """
        try:
            if idx not in self.process_managers:
                self.logger.warning(f"设备{idx}的进程管理器不存在")
                return False, DeviceStatus.NOT_FOUND

            # 检查进程是否在运行
            if not await self.process_managers[idx].is_running():
                self.logger.info(f"设备{idx}进程已经停止")
                return True, DeviceStatus.OFFLINE

            # 终止进程
            await self.process_managers[idx].kill(if_force=False)

            # 等待进程完全停止
            stop_time = datetime.now()
            timeout = timedelta(seconds=10)  # 10秒超时

            while datetime.now() - stop_time < timeout:
                if not await self.process_managers[idx].is_running():
                    # 清理设备信息
                    if idx in self.device_info:
                        del self.device_info[idx]

                    self.logger.info(f"设备{idx}已成功关闭")
                    return True, DeviceStatus.OFFLINE

                await asyncio.sleep(0.1)

            # 强制终止
            self.logger.warning(f"设备{idx}未能正常关闭，尝试强制终止")
            await self.process_managers[idx].kill(if_force=True)

            if idx in self.device_info:
                del self.device_info[idx]

            return True, DeviceStatus.OFFLINE

        except Exception as e:
            self.logger.error(f"关闭设备{idx}失败: {str(e)}")
            return False, DeviceStatus.ERROR

    async def get_status(self, idx: str) -> int:
        """
        获取指定设备当前状态

        Args:
            idx: 设备ID

        Returns:
            int: 状态码
        """
        try:
            if idx not in self.process_managers:
                return DeviceStatus.OFFLINE

            if await self.process_managers[idx].is_running():
                return DeviceStatus.ONLINE
            else:
                return DeviceStatus.OFFLINE

        except Exception as e:
            self.logger.error(f"获取设备{idx}状态失败: {str(e)}")
            return DeviceStatus.ERROR

    async def hide_device(self, idx: str) -> tuple[bool, int]:
        """
        隐藏设备窗口

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """
        try:
            status = await self.get_status(idx)
            if status != DeviceStatus.ONLINE:
                return False, status

            if (
                idx not in self.process_managers
                or not self.process_managers[idx].main_pid
            ):
                return False, DeviceStatus.NOT_FOUND

            # 窗口隐藏功能（简化实现）
            # 注意：完整的窗口隐藏功能需要更复杂的Windows API调用
            self.logger.info(f"设备{idx}窗口隐藏请求已处理（简化实现）")
            return True, DeviceStatus.ONLINE

            self.logger.info(f"设备{idx}窗口已隐藏")
            return True, DeviceStatus.ONLINE

        except ImportError:
            self.logger.warning("隐藏窗口功能需要pywin32库")
            return False, DeviceStatus.ERROR
        except Exception as e:
            self.logger.error(f"隐藏设备{idx}窗口失败: {str(e)}")
            return False, DeviceStatus.ERROR

    async def show_device(self, idx: str) -> tuple[bool, int]:
        """
        显示设备窗口

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """
        try:
            status = await self.get_status(idx)
            if status != DeviceStatus.ONLINE:
                return False, status

            if (
                idx not in self.process_managers
                or not self.process_managers[idx].main_pid
            ):
                return False, DeviceStatus.NOT_FOUND

            # 窗口显示功能（简化实现）
            # 注意：完整的窗口显示功能需要更复杂的Windows API调用
            self.logger.info(f"设备{idx}窗口显示请求已处理（简化实现）")
            return True, DeviceStatus.ONLINE

            self.logger.info(f"设备{idx}窗口已显示")
            return True, DeviceStatus.ONLINE

        except ImportError:
            self.logger.warning("显示窗口功能需要pywin32库")
            return False, DeviceStatus.ERROR
        except Exception as e:
            self.logger.error(f"显示设备{idx}窗口失败: {str(e)}")
            return False, DeviceStatus.ERROR

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        """
        获取所有设备信息

        Returns:
            dict[str, dict[str, str]]: 设备信息字典
            结构示例:
            {
                "0": {
                    "title": "设备名称",
                    "status": "1"
                }
            }
        """
        result = {}

        for idx in list(self.process_managers.keys()):
            try:
                status = await self.get_status(idx)

                if idx in self.device_info:
                    title = self.device_info[idx].get("title", f"{self.name}_{idx}")
                else:
                    title = f"{self.name}_{idx}"

                result[idx] = {"title": title, "status": str(status)}

            except Exception as e:
                self.logger.error(f"获取设备{idx}信息失败: {str(e)}")
                result[idx] = {
                    "title": f"{self.name}_{idx}",
                    "status": str(DeviceStatus.ERROR),
                }

        return result

    async def cleanup(self) -> None:
        """
        清理所有资源
        """
        self.logger.info("开始清理设备管理器资源")

        for idx, pm in list(self.process_managers.items()):
            try:
                if await pm.is_running():
                    await pm.kill(if_force=True)
                await pm.clear()
            except Exception as e:
                self.logger.error(f"清理设备{idx}资源失败: {str(e)}")

        self.process_managers.clear()
        self.device_info.clear()

        self.logger.info("设备管理器资源清理完成")

    def __del__(self):
        """析构函数，确保资源被正确释放"""
        try:
            # 注意：析构函数中不能使用async/await
            # 这里只是标记，实际清理需要显式调用cleanup()
            if hasattr(self, "process_managers") and self.process_managers:
                self.logger.warning("设备管理器未正确清理，请显式调用cleanup()方法")
        except:  # noqa: E722
            pass
