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


import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from app.utils.ProcessManager import ProcessManager
from app.models.emulator import DeviceStatus, DeviceBase
from app.models.config import EmulatorConfig
from app.utils.logger import get_logger

logger = get_logger("通用模拟器管理")


class GeneralDeviceManager(DeviceBase):
    """
    用于管理一般应用程序进程
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
        self.process_managers: Dict[str, ProcessManager] = {}
        self.device_info: Dict[str, Dict[str, Any]] = {}

    async def open(self, idx: str) -> tuple[bool, int, dict]:
        """
        启动设备

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int, dict]: (是否成功, 状态码, 启动信息)
        """

        # 检查是否已经在运行
        current_status = await self.get_status(idx)
        if current_status in [DeviceStatus.ONLINE, DeviceStatus.STARTING]:
            logger.warning(f"设备{idx}已经在运行，状态: {current_status}")
            return False, current_status, {}

        # 创建进程管理器
        if idx not in self.process_managers:
            self.process_managers[idx] = ProcessManager()

        # 准备启动参数

        # 启动进程
        await self.process_managers[idx].open_process(
            self.emulator_path, idx.split(), tracking_time=0
        )

        # 等待进程启动
        start_time = datetime.now()

        while datetime.now() - start_time < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            if await self.process_managers[idx].is_running():
                self.device_info[idx] = {
                    "title": f"{self.config.get('Info', 'Name')}_{idx}",
                    "status": str(DeviceStatus.ONLINE),
                    "pid": self.process_managers[idx].main_pid,
                    "start_time": start_time.isoformat(),
                }

                logger.info(f"设备{idx}启动成功")
                return True, DeviceStatus.ONLINE, self.device_info[idx]

            await asyncio.sleep(0.1)

        logger.error(f"设备{idx}启动超时")
        return False, DeviceStatus.ERROR, {}

    async def close(self, idx: str) -> tuple[bool, int]:
        """
        关闭设备或服务

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """

        if idx not in self.process_managers:
            logger.warning(f"设备{idx}的进程管理器不存在")
            return False, DeviceStatus.NOT_FOUND

        # 检查进程是否在运行
        if not await self.process_managers[idx].is_running():
            logger.info(f"设备{idx}进程已经停止")
            return True, DeviceStatus.OFFLINE

        # 终止进程
        await self.process_managers[idx].kill(if_force=False)

        # 等待进程完全停止
        stop_time = datetime.now()

        while datetime.now() - stop_time < timedelta(
            seconds=self.config.get("Data", "MaxWaitTime")
        ):
            if not await self.process_managers[idx].is_running():
                # 清理设备信息
                if idx in self.device_info:
                    del self.device_info[idx]

                logger.info(f"设备{idx}已成功关闭")
                return True, DeviceStatus.OFFLINE

            await asyncio.sleep(0.1)

        # 强制终止
        logger.warning(f"设备{idx}未能正常关闭，尝试强制终止")
        await self.process_managers[idx].kill(if_force=True)

        if idx in self.device_info:
            del self.device_info[idx]

        return True, DeviceStatus.OFFLINE

    async def get_status(self, idx: str) -> int:
        """
        获取指定设备当前状态

        Args:
            idx: 设备ID

        Returns:
            int: 状态码
        """

        if idx not in self.process_managers:
            return DeviceStatus.OFFLINE

        if await self.process_managers[idx].is_running():
            return DeviceStatus.ONLINE
        else:
            return DeviceStatus.OFFLINE

    async def hide_device(self, idx: str):
        """
        隐藏设备窗口

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """
        # try:
        #     status = await self.get_status(idx)
        #     if status != DeviceStatus.ONLINE:
        #         return False, status

        #     if (
        #         idx not in self.process_managers
        #         or not self.process_managers[idx].main_pid
        #     ):
        #         return False, DeviceStatus.NOT_FOUND

        #     # 窗口隐藏功能（简化实现）
        #     # 注意：完整的窗口隐藏功能需要更复杂的Windows API调用
        #     self.logger.info(f"设备{idx}窗口隐藏请求已处理（简化实现）")
        #     return True, DeviceStatus.ONLINE

        #     self.logger.info(f"设备{idx}窗口已隐藏")
        #     return True, DeviceStatus.ONLINE

        # except ImportError:
        #     self.logger.warning("隐藏窗口功能需要pywin32库")
        #     return False, DeviceStatus.ERROR
        # except Exception as e:
        #     self.logger.error(f"隐藏设备{idx}窗口失败: {str(e)}")
        #     return False, DeviceStatus.ERROR

    async def show_device(self, idx: str):
        """
        显示设备窗口

        Args:
            idx: 设备ID

        Returns:
            tuple[bool, int]: (是否成功, 状态码)
        """
        # try:
        #     status = await self.get_status(idx)
        #     if status != DeviceStatus.ONLINE:
        #         return False, status

        #     if (
        #         idx not in self.process_managers
        #         or not self.process_managers[idx].main_pid
        #     ):
        #         return False, DeviceStatus.NOT_FOUND

        #     # 窗口显示功能（简化实现）
        #     # 注意：完整的窗口显示功能需要更复杂的Windows API调用
        #     self.logger.info(f"设备{idx}窗口显示请求已处理（简化实现）")
        #     return True, DeviceStatus.ONLINE

        #     self.logger.info(f"设备{idx}窗口已显示")
        #     return True, DeviceStatus.ONLINE

        # except ImportError:
        #     self.logger.warning("显示窗口功能需要pywin32库")
        #     return False, DeviceStatus.ERROR
        # except Exception as e:
        #     self.logger.error(f"显示设备{idx}窗口失败: {str(e)}")
        #     return False, DeviceStatus.ERROR

    async def get_all_info(self) -> dict[str, dict[str, str]]:
        """
        获取所有设备信息
        """

        return {}

    async def cleanup(self) -> None:
        """
        清理所有资源
        """
        logger.info("开始清理设备管理器资源")

        for idx, pm in self.process_managers.items():
            try:
                if await pm.is_running():
                    await pm.kill(if_force=True)
            except Exception as e:
                logger.error(f"清理设备{idx}资源失败: {str(e)}")

        self.process_managers.clear()
        self.device_info.clear()

        logger.info("设备管理器资源清理完成")
