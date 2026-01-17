#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

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
from datetime import datetime

from app.services import Matomo
from app.utils import get_logger
from .config import Config
from .task_manager import TaskManager


logger = get_logger("主业务定时器")


class _MainTimer:

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

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
                    Config.VERSION,
                    1 if "beta" in Config.VERSION else 0,
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

            if not queue.get("Info", "TimeEnabled"):
                continue

            # 避免重复调起任务
            if curtime == queue.get("Data", "LastTimedStart"):
                continue

            for time_set in queue.TimeSet.values():
                if time_set.get("Info", "Enabled") and curtime[11:16] == time_set.get(
                    "Info", "Time"
                ):
                    logger.info(f"定时唤起任务：{uid}")
                    task_id = await TaskManager.add_task("AutoProxy", str(uid))
                    await queue.set("Data", "LastTimedStart", curtime)
                    await Config.QueueConfig.save()

                    await Config.send_websocket_message(
                        id="TaskManager",
                        type="Signal",
                        data={
                            "newTask": str(task_id),
                            "queueId": str(uid),
                            "taskName": f"队列 - {queue.get('Info', 'Name')}",
                            "taskType": "定时代理",
                        },
                    )


MainTimer = _MainTimer()
