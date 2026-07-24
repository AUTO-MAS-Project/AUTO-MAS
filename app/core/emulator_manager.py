#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Literal

from app.core import Config
from .ws import Publisher, protocol
from app.models.emulator import DeviceBase, EmulatorRuntimeConfig
from app.models.schema import DeviceInfo as SchemaDeviceInfo, WSTaskNoticeData
from app.utils import ProcessRunner, EMULATOR_TYPE_BOOK
from app.utils.constants import EMULATOR_SPLASH_ADS_PATH_BOOK

from app.utils import get_logger


logger = get_logger("模拟器管理")


class _EmulatorManager:
    """模拟器实例管理器"""

    def __init__(self) -> None:
        # 跟踪每个 (emulator_id:index) 的 in-flight 操作，避免无界后台 task
        self._inflight: Dict[str, asyncio.Task] = {}

    async def _load_emulator_config(
        self,
        emulator_id: str,
    ) -> EmulatorRuntimeConfig:
        """加载并校验模拟器配置（无副作用，仅校验 UUID / 类型）。

        Raises:
            ValueError: UUID 非法或不支持的模拟器类型
            KeyError: 未找到配置项
        """

        emulator_uid = uuid.UUID(emulator_id)

        config = EmulatorRuntimeConfig.from_mapping(
            await Config.EmulatorConfig[emulator_uid].toDict()
        )

        if config.get("Info", "Type") not in EMULATOR_TYPE_BOOK:
            raise ValueError(f"不支持的模拟器类型: {config.get('Info', 'Type')}")
        return config

    async def _apply_ad_blocking(
        self,
        config: EmulatorRuntimeConfig,
    ) -> None:
        """应用广告屏蔽副作用（best-effort，异常可见不掩盖）。

        仅捕获确属非关键副作用的异常并记录日志，不影响实例构造。
        """

        emu_type = config.get("Info", "Type")

        if emu_type in EMULATOR_SPLASH_ADS_PATH_BOOK:
            ads_paths = EMULATOR_SPLASH_ADS_PATH_BOOK[emu_type]
            try:
                if Config.get("Function", "IfBlockAd"):
                    for ads_path in ads_paths:
                        if ads_path.is_dir():
                            shutil.rmtree(ads_path)
                        ads_path.parent.mkdir(parents=True, exist_ok=True)
                        ads_path.touch()
                else:
                    for ads_path in ads_paths:
                        if ads_path.is_file():
                            ads_path.unlink()
            except (OSError, PermissionError) as e:
                logger.warning(
                    f"模拟器广告屏蔽文件操作失败 (type={emu_type}): {e}"
                )

        if emu_type == "ldplayer":
            try:
                await ProcessRunner.run_process(
                    Path(config.get("Info", "Path")),
                    "globalsetting",
                    "--cleanmode",
                    "1" if Config.get("Function", "IfBlockAd") else "0",
                    timeout=config.get("Info", "MaxWaitTime"),
                )
            except (RuntimeError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"ldplayer globalsetting 调用失败: {e}")

    async def get_emulator_instance(self, emulator_id: str) -> DeviceBase:
        """加载配置、应用广告屏蔽副作用并构造模拟器实例。"""

        config = await self._load_emulator_config(emulator_id)
        await self._apply_ad_blocking(config)
        return EMULATOR_TYPE_BOOK[config.get("Info", "Type")](config)

    async def operate_emulator(
        self, operate: Literal["open", "close", "show"], emulator_id: str, index: str
    ) -> str:
        """同步校验后派发后台操作，返回 operation_id。

        校验失败立即抛异常（消除假成功）；校验通过返回 accepted 的 operation_id，
        真实结果通过 WS ``emulator.notice`` 携带 ``operationId`` 推送。

        Raises:
            ValueError: UUID 非法或不支持的模拟器类型
            KeyError: 未找到配置项
            FileNotFoundError: 模拟器路径不存在
            RuntimeError: 该设备已有操作进行中
        """

        config = await self._load_emulator_config(emulator_id)

        if not Path(config.get("Info", "Path")).exists():
            raise FileNotFoundError(
                f"模拟器路径不存在: {config.get('Info', 'Path')}"
            )

        operation_id = str(uuid.uuid4())
        device_key = f"{emulator_id}:{index}"
        existing = self._inflight.get(device_key)
        if existing is not None and not existing.done():
            raise RuntimeError(f"模拟器 {device_key} 已有操作进行中")

        task = asyncio.create_task(
            self._run_operate(operate, emulator_id, index, operation_id)
        )
        self._inflight[device_key] = task
        task.add_done_callback(lambda t: self._inflight.pop(device_key, None))
        return operation_id

    async def _run_operate(
        self,
        operate: Literal["open", "close", "show"],
        emulator_id: str,
        index: str,
        operation_id: str,
    ) -> None:
        """后台执行模拟器操作，完成后通过 WS 推送结果。"""

        try:
            temp_emulator = await self.get_emulator_instance(emulator_id)

            if operate == "open":
                await temp_emulator.open(index)
            elif operate == "close":
                await temp_emulator.close(index)
            elif operate == "show":
                await temp_emulator.setVisible(index, True)

            await Publisher.send(
                id=protocol.ID_EMULATOR_MANAGER,
                type=protocol.EMULATOR_NOTICE,
                data=WSTaskNoticeData(
                    level="info",
                    message=f"模拟器操作完成: {operate}",
                    operationId=operation_id,
                ),
            )
        except Exception as e:
            logger.warning(
                f"模拟器操作失败 operation={operation_id}: {type(e).__name__}: {e}"
            )
            try:
                await Publisher.send(
                    id=protocol.ID_EMULATOR_MANAGER,
                    type=protocol.EMULATOR_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"模拟器操作失败: {e}",
                        operationId=operation_id,
                    ),
                )
            except Exception as ws_err:
                logger.warning(
                    f"WS 推送失败 operation={operation_id}: {type(ws_err).__name__}: {ws_err}"
                )

    async def get_status(
        self, emulator_id: str | None = None
    ) -> Dict[str, Dict[str, SchemaDeviceInfo]]:
        """查询模拟器状态，单个损坏配置/失联实例不阻断整列。"""

        if emulator_id is None:
            emulator_range = list(map(str, Config.EmulatorConfig.keys()))
        else:
            emulator_range = [emulator_id]

        data: Dict[str, Dict[str, SchemaDeviceInfo]] = {}
        for eid in emulator_range:
            try:
                temp_emulator = await self.get_emulator_instance(eid)
                emulator_device_info = await temp_emulator.getInfo(None)

                converted_devices: Dict[str, SchemaDeviceInfo] = {}
                for device_index, device_info in emulator_device_info.items():
                    converted_devices[device_index] = SchemaDeviceInfo(
                        title=device_info.title,
                        status=int(device_info.status),
                        adb_address=device_info.adb_address,
                    )
                data[eid] = converted_devices
            except Exception as e:
                logger.warning(
                    f"获取模拟器 {eid} 状态失败，已隔离: {type(e).__name__}: {e}"
                )
                data[eid] = {}

        return data


EmulatorManager = _EmulatorManager()
