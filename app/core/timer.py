#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361

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
import keyboard
from datetime import datetime

from app.services import Matomo, System
from app.utils import get_logger
from app.models.schema import WebSocketMessage
from .config import Config, QueueConfig
from .task_manager import TaskManager


logger = get_logger("主业务定时器")


class _MainTimer:

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

            await self.set_silence()
            await self.timed_start()

            await asyncio.sleep(1)

    async def hour_task(self):
        """每小时定期任务"""

        logger.info("每小时定期任务启动")

        while True:

            if (
                datetime.strptime(
                    Config.get("Data", "LastStatisticsUpload"), "%Y-%m-%d %H:%M:%S"
                ).date()
                != datetime.now().date()
            ):
                await Matomo.send_event(
                    "App",
                    "Version",
                    Config.version(),
                    1 if "beta" in Config.version() else 0,
                )
                await Config.set(
                    "Data",
                    "LastStatisticsUpload",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )

            await asyncio.sleep(3600)

    @logger.catch()
    async def timed_start(self):
        """定时启动代理任务"""

        curtime = datetime.now().strftime("%Y-%m-%d %H:%M")

        for uid, queue in Config.QueueConfig.items():

            if not isinstance(queue, QueueConfig) or not queue.get(
                "Info", "TimeEnabled"
            ):
                continue

            # 避免重复调起任务
            if curtime == queue.get("Data", "LastTimedStart"):
                continue

            for time_set in queue.TimeSet.values():
                if (
                    time_set.get("Info", "Enabled")
                    and curtime[11:16] == time_set.get("Info", "Time")
                    and uid not in Config.task_dict
                ):
                    logger.info(f"定时唤起任务：{uid}")
                    task_id = await TaskManager.add_task("自动代理", str(uid))
                    await queue.set("Data", "LastTimedStart", curtime)
                    await Config.QueueConfig.save()

                    await Config.send_json(
                        WebSocketMessage(
                            id="TaskManager",
                            type="Signal",
                            data={"newTask": str(task_id)},
                        ).model_dump()
                    )

    async def set_silence(self):
        """静默模式通过模拟老板键来隐藏模拟器窗口"""

        logger.debug("检查静默模式")

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

        logger.debug("静默模式检查完毕")


MainTimer = _MainTimer()
