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
import asyncio
from typing import Dict, Literal

from .config import Config
from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase
from app.models.schema import DeviceInfo as SchemaDeviceInfo
from app.utils import EMULATOR_TYPE_BOOK

from app.utils import get_logger


logger = get_logger("模拟器管理")


class _EmulatorManager:
    """模拟器实例管理器"""

    async def get_emulator_instance(self, emulator_id: str) -> DeviceBase:

        emulator_uid = uuid.UUID(emulator_id)

        config = EmulatorConfig()
        await config.load(await Config.EmulatorConfig[emulator_uid].toDict())
        if config.get("Data", "Type") in EMULATOR_TYPE_BOOK:
            return EMULATOR_TYPE_BOOK[config.get("Data", "Type")](config)
        else:
            raise ValueError(f"不支持的模拟器类型: {config.get('Data', 'Type')}")

    async def operate_emulator(
        self, operate: Literal["open", "close"], emulator_id: str, index: str
    ):

        asyncio.create_task(self.operate_emulator_task(operate, emulator_id, index))

    async def operate_emulator_task(
        self, operate: Literal["open", "close"], emulator_id: str, index: str
    ):

        try:
            temp_emulator = await self.get_emulator_instance(emulator_id)
            if temp_emulator is None:
                raise KeyError(f"未找到UUID为 {emulator_id} 的模拟器配置")

            if operate == "open":
                await temp_emulator.open(index)
            elif operate == "close":
                await temp_emulator.close(index)
        except Exception as e:
            await Config.send_websocket_message(
                id="EmulatorManager",
                type="Info",
                data={"error": f"模拟器操作失败: {str(e)}"},
            )

    async def get_status(
        self, emulator_id: str | None = None
    ) -> Dict[str, Dict[str, SchemaDeviceInfo]]:

        if emulator_id is None:
            emulator_range = list(map(str, Config.EmulatorConfig.keys()))
        else:
            emulator_range = [emulator_id]

        data = {}
        for emulator_id in emulator_range:
            temp_emulator = await self.get_emulator_instance(emulator_id)
            emulator_device_info = await temp_emulator.getInfo(None)

            # 转换 EmulatorDeviceInfo 到 SchemaDeviceInfo
            converted_devices = {}
            for device_index, device_info in emulator_device_info.items():
                converted_devices[device_index] = SchemaDeviceInfo(
                    title=device_info.title,
                    status=int(device_info.status),
                    adb_address=device_info.adb_address,
                )

            data[emulator_id] = converted_devices

        return data


EmulatorManager = _EmulatorManager()
