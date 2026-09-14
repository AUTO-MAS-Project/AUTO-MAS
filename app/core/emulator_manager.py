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


import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Dict, Literal

from app.models.config import EmulatorConfig
from app.models.emulator import DeviceBase
from app.models.schema import DeviceInfo as SchemaDeviceInfo
from app.models.schema import WSEmulatorOperationData, WSTaskNoticeData
from app.utils import EMULATOR_TYPE_BOOK, ProcessRunner, get_logger
from app.utils.constants import EMULATOR_SPLASH_ADS_PATH_BOOK

from .config import Config
from .ws import Publisher, protocol

logger = get_logger("模拟器管理")


class _EmulatorManager:
    """模拟器实例管理器"""

    async def get_emulator_instance(self, emulator_id: str) -> DeviceBase:

        emulator_uid = uuid.UUID(emulator_id)

        config = EmulatorConfig()
        await config.load(await Config.EmulatorConfig[emulator_uid].toDict())

        if config.get("Info", "Type") in EMULATOR_TYPE_BOOK:
            # 设置模拟器广告, 失败不影响模拟器实例创建, 但要留下原因
            try:
                if config.get("Info", "Type") in EMULATOR_SPLASH_ADS_PATH_BOOK:
                    ads_paths = EMULATOR_SPLASH_ADS_PATH_BOOK[
                        config.get("Info", "Type")
                    ]
                    if Config.get("Function", "IfBlockAd"):
                        for ads_path in ads_paths:
                            if ads_path.is_dir():
                                await asyncio.to_thread(shutil.rmtree, ads_path)
                            ads_path.parent.mkdir(parents=True, exist_ok=True)
                            ads_path.touch()
                    else:
                        for ads_path in ads_paths:
                            if ads_path.is_file():
                                ads_path.unlink()
                if config.get("Info", "Type") == "ldplayer":
                    await ProcessRunner.run_process(
                        Path(config.get("Info", "Path")),
                        "globalsetting",
                        "--cleanmode",
                        "1" if Config.get("Function", "IfBlockAd") else "0",
                        timeout=config.get("Info", "MaxWaitTime"),
                    )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"设置模拟器去广告失败: {type(e).__name__}: {e}")

            return EMULATOR_TYPE_BOOK[config.get("Info", "Type")](config)
        else:
            raise ValueError(f"不支持的模拟器类型: {config.get('Info', 'Type')}")

    async def operate_emulator(
        self,
        operate: Literal["open", "close", "show", "hide"],
        emulator_id: str,
        index: str,
    ):

        asyncio.create_task(self.operate_emulator_task(operate, emulator_id, index))

    async def operate_emulator_task(
        self,
        operate: Literal["open", "close", "show", "hide"],
        emulator_id: str,
        index: str,
    ):
        """跑一次启动 / 关闭 / 显示 / 隐藏。

        接口一调用就返回，这里才是真正干活的地方：启动要等到 Android 起来，
        动辄几十秒。结束时（不论成败）发一条 ``emulator.operation.finished``，
        界面靠它收掉「启动中」之类的过渡态；失败另外照旧弹一条错误提示。
        """
        error = ""
        try:
            temp_emulator = await self.get_emulator_instance(emulator_id)
            if temp_emulator is None:
                raise KeyError(f"未找到UUID为 {emulator_id} 的模拟器配置")

            if operate == "open":
                await temp_emulator.open(index)
            elif operate == "close":
                await temp_emulator.close(index)
            elif operate == "show":
                await temp_emulator.setVisible(index, True)
            elif operate == "hide":
                await temp_emulator.setVisible(index, False)
        except Exception as e:
            error = str(e)
            await Publisher.send(
                id=protocol.ID_EMULATOR_MANAGER,
                type=protocol.EMULATOR_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"模拟器操作失败: {str(e)}"
                ),
            )
        await Publisher.send(
            id=protocol.ID_EMULATOR_MANAGER,
            type=protocol.EMULATOR_OPERATION_FINISHED,
            data=WSEmulatorOperationData(
                emulatorId=emulator_id,
                index=index,
                operate=operate,
                ok=not error,
                message=error,
            ),
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
