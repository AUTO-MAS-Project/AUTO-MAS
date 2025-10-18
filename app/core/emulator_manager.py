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


import uuid


from .config import Config
from app.models.emulator import DeviceBase, DeviceStatus
from app.utils import EMULATOR_TYPE_BOOK

from app.utils import get_logger


logger = get_logger("模拟器管理")


class _EmulatorManager:
    """模拟器实例管理器"""

    async def get_emulator_instance(self, emulator_id: str) -> DeviceBase:
        """
        创建模拟器管理器实例

        Parameters
        ----------
        emulator_id : str
            配置项的UUID
        """

        emulator_uid = uuid.UUID(emulator_id)

        config = Config.EmulatorData[emulator_uid]
        if config.get("Data", "Type") in EMULATOR_TYPE_BOOK:
            return EMULATOR_TYPE_BOOK[config.get("Data", "Type")](config)
        else:
            raise ValueError(f"不支持的模拟器类型: {config.get('Data', 'Type')}")

    async def open_emulator(self, emulator_id: str, index: str, package_name: str = ""):
        """
        根据UUID和模拟器索引打开指定模拟器

        Parameters
        ----------
        emulator_id : str
            配置项的UUID
        index : str
            模拟器索引
        package_name : str, optional
            启动指定包名, by default ""
        """

        temp_emulator = await self.get_emulator_instance(emulator_id)
        if temp_emulator is None:
            raise KeyError(f"未找到UUID为 {emulator_id} 的模拟器配置")

        # 调用模拟器实例的start方法启动指定索引的模拟器
        success, status, info = await temp_emulator.open(index, package_name)

        if success:
            logger.success(
                f"成功启动模拟器，索引: {index}，状态: {DeviceStatus(status).name}"
            )
        else:
            logger.error(
                f"启动模拟器失败，索引: {index}，状态: {DeviceStatus(status).name}"
            )

        return success, info

    async def close_emulator(self, emulator_id: str, index: str):
        """
        根据UUID和模拟器索引关闭指定模拟器

        Parameters
        ----------
        emulator_id : str
            配置项的UUID
        index : str
            模拟器索引
        """

        temp_emulator = await self.get_emulator_instance(emulator_id)
        if temp_emulator is None:
            raise KeyError(f"未找到UUID为 {emulator_id} 的模拟器配置")

        # 调用模拟器实例的close方法关闭指定索引的模拟器
        success, status = await temp_emulator.close(index)

        if success:
            logger.success(
                f"成功关闭模拟器，索引: {index}，状态: {DeviceStatus(status).name}"
            )
        else:
            logger.error(
                f"关闭模拟器失败，索引: {index}，状态: {DeviceStatus(status).name}"
            )

        return success, status

    async def get_emulator_status(self, emulator_id: str | None = None):
        """
        获取模拟器的状态

        Returns:
            tuple[bool, str]: (是否成功, 状态信息)
        """

        if emulator_id is None:
            emulator_range = list(map(str, Config.EmulatorData.keys()))
        else:
            emulator_range = [emulator_id]

        data = {}
        for emulator_id in emulator_range:
            temp_emulator = await self.get_emulator_instance(emulator_id)
            data[emulator_id] = await temp_emulator.get_all_info()

        return data


EmulatorManager = _EmulatorManager()
