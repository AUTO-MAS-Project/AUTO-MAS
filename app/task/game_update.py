#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""模拟器游戏更新任务，与代理状态、账号前后置脚本分开执行。"""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.models.ConfigBase import ConfigBase
from app.models.emulator import DeviceBase, DeviceStatus
from app.models.task import ScriptItem, TaskExecuteBase
from app.task.emulator_core import close_emulator
from app.utils import get_logger
from app.utils.game_apk import GameUpdateResult

logger = get_logger("游戏更新任务")


class EmulatorGameUpdateTask(TaskExecuteBase):
    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        *,
        script_info: ScriptItem,
        script_config: ConfigBase,
        emulator_manager: DeviceBase,
        server: str,
        package_name: str,
        checker: Callable[..., Awaitable[GameUpdateResult]],
    ) -> None:
        super().__init__()
        self.script_info = script_info
        self.script_config = script_config
        # 更新可能早于代理配置锁；清理必须始终指向本次实际启动的设备。
        self.emulator_index = script_config.get("Emulator", "Index")
        self.time_limit = script_config.get("Run", "GameUpdateTimeLimit")
        self.if_auto_install = script_config.get("Run", "IfAutoInstallGameApk")
        self.emulator_manager = emulator_manager
        self.server = server
        self.package_name = package_name
        self.checker = checker
        self.result: GameUpdateResult | None = None
        self.owns_emulator = False

    async def _report(self, message: str) -> None:
        self.script_info.log = message
        logger.info(message)

    async def main_task(self) -> None:
        async with asyncio.timeout(self.time_limit * 60):
            self.owns_emulator = (
                await self.emulator_manager.getStatus(self.emulator_index)
                == DeviceStatus.OFFLINE
            )
            # 不传游戏包名，只启动设备供版本检查和 APK 安装使用。
            info = await self.emulator_manager.open(self.emulator_index)
            self.result = await self.checker(
                adb_path=self.emulator_manager.get_adb_path(),
                adb_address=info.adb_address,
                server=self.server,
                package_name=self.package_name,
                apk_dir=Path.cwd() / "data/GameApk",
                if_auto_install=self.if_auto_install,
                time_limit=self.time_limit,
                progress=self._report,
            )
            await self._report(self.result.message)

    async def close_owned_emulator(self) -> None:
        if self.owns_emulator:
            if await close_emulator(self, index=self.emulator_index):
                self.owns_emulator = False

    async def final_task(self) -> None:
        # 正常完成后留给代理复用设备；维护跳过由 manager 关闭本次启动的设备。
        if self.stopped_manually or self.result is None:
            await self.close_owned_emulator()

    async def on_crash(self, error: Exception) -> None:
        logger.opt(exception=True).warning(f"游戏更新检查异常，沿用原代理流程: {error}")
        self.script_info.log = f"游戏更新检查异常: {error}"
