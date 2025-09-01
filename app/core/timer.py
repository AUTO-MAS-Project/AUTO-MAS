#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

import asyncio
import keyboard
from datetime import datetime

from app.services import System
from app.utils import get_logger
from .config import Config


logger = get_logger("主业务定时器")


class _MainTimer:

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

            await self.set_silence()

            await asyncio.sleep(1)

    async def set_silence(self):
        """静默模式通过模拟老板键来隐藏模拟器窗口"""

        if (
            len(Config.if_ignore_silence) > 0
            and Config.get("Function", "IfSilence")
            and Config.get("Function", "BossKey") != ""
        ):

            windows = await System.get_window_info()

            emulator_windows = []
            for window in windows:
                for emulator_path, endtime in Config.silence_dict.items():
                    if (
                        datetime.now() < endtime
                        and str(emulator_path) in window
                        and window[0] != "新通知"  # 此处排除雷电名为新通知的窗口
                    ):
                        emulator_windows.append(window)

            if emulator_windows:

                logger.info(f"检测到模拟器窗口: {emulator_windows}")
                try:
                    keyboard.press_and_release(
                        "+".join(
                            _.strip().lower()
                            for _ in Config.get("Function", "BossKey").split("+")
                        )
                    )
                    logger.info(f"模拟按键: {Config.get('Function', 'BossKey')}")
                except Exception as e:
                    logger.exception(f"模拟按键时出错: {e}")


MainTimer = _MainTimer()
