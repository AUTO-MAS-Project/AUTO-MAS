#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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
import json
import random
from datetime import datetime, timedelta

from app.services import Matomo
from app.MaaFW import ArknightWin32Toolkit
from app.utils import get_logger
from .config import Config
from .task_manager import TaskManager


logger = get_logger("主业务定时器")


class _MainTimer:

    def __init__(self):
        self.started = False

    async def start(self):
        """启动定时器"""

        if self.started:
            logger.warning("主业务定时器仅能启动一次，无法重复启动")
            return

        self.second_timer = asyncio.create_task(MainTimer.second_task())
        self.hour_timer = asyncio.create_task(MainTimer.hour_task())
        self.started = True
        logger.info("主业务定时器启动")

    async def stop(self):
        """停止定时器"""

        self.second_timer.cancel()
        self.hour_timer.cancel()
        try:
            await self.second_timer
            await self.hour_timer
        except asyncio.CancelledError:
            logger.info("主业务定时器已关闭")

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

            await self.timed_start()

            if Config.ToolsConfig.get("ArknightsPC", "Enabled"):
                await ArknightWin32Toolkit.scheduled_task()

            await self.check_game_sign()

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
        curday = datetime.now().strftime("%A")

        for uid, queue in Config.QueueConfig.items():

            if not queue.get("Info", "TimeEnabled"):
                continue

            # 避免重复调起任务
            if curtime == queue.get("Data", "LastTimedStart"):
                continue

            for time_set in queue.TimeSet.values():
                if (
                    time_set.get("Info", "Enabled")
                    and curday in time_set.get("Info", "Days")
                    and curtime[11:16] == time_set.get("Info", "Time")
                ):
                    logger.info(f"定时唤起任务：{uid}")
                    await TaskManager.add_task(
                        "AutoProxy",
                        str(uid),
                        new_task_info={
                            "queueId": str(uid),
                            "taskName": f"队列 - {queue.get('Info', 'Name')}",
                            "taskType": "定时代理",
                        },
                    )
                    await queue.set("Data", "LastTimedStart", curtime)

                    # 定时任务触发游戏签到
                    await self.try_game_sign_for_task()

    async def check_game_sign(self) -> None:
        """检查并执行游戏社区签到

        启用签到 + 时间窗口内随机时刻执行，窗口外补签。
        仅在整分钟时执行（秒数 != 0 时跳过），因为调度精度为分钟级。
        """

        if not Config.ToolsConfig.get("GameSign", "Enabled"):
            return

        # 节流：非整分钟跳过，避免每秒都执行
        if datetime.now().second != 0:
            return

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 检查是否所有启用的用户今日都已签到
        all_users_signed = True
        for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
            if account.get("GameSignAccount", "Enabled"):
                if account.get("GameSignAccount", "LastSignDate") != today:
                    all_users_signed = False
                    break

        if all_users_signed:
            return

        # 解析签到窗口
        try:
            window_start_str = Config.ToolsConfig.get("GameSign", "WindowStart")
            window_end_str = Config.ToolsConfig.get("GameSign", "WindowEnd")
            window_start = datetime.strptime(window_start_str, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
            window_end = datetime.strptime(window_end_str, "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
        except (ValueError, TypeError):
            return

        # 如果在窗口开始之前，跳过
        if now < window_start:
            return

        # 如果在窗口结束之后，立即补签
        if now > window_end:
            await self._execute_game_sign()
            return

        # 确定计划签到时间
        scheduled_time_str = Config.ToolsConfig.get("GameSign", "ScheduledTime")

        if not scheduled_time_str:
            # 首次进入窗口：计算今天的随机时间
            remaining_seconds = int((window_end - now).total_seconds())
            if remaining_seconds <= 0:
                await self._execute_game_sign()
                return
            random_offset = random.randint(0, remaining_seconds)
            scheduled_time = now + timedelta(seconds=random_offset)
            await Config.ToolsConfig.set(
                "GameSign", "ScheduledTime", scheduled_time.strftime("%H:%M")
            )
            return

        # 检查是否到达计划时间（分钟精度）
        if now.strftime("%H:%M") == scheduled_time_str:
            await self._execute_game_sign()
            # Prevent duplicate trigger within same minute
            await Config.ToolsConfig.set("GameSign", "ScheduledTime", "")

    async def _execute_game_sign(self) -> None:
        """执行游戏签到并处理结果"""
        from app.tools.game_sign import run_all_sign_in, format_sign_results
        from app.tools.game_sign import merge_sign_results

        today = datetime.now().strftime("%Y-%m-%d")

        try:
            logger.info("开始执行游戏社区签到")
            results = await run_all_sign_in(force=False)

            # 如果所有用户都已签到（无新结果），保留已有结果
            if not results:
                logger.info("所有用户今日已签到，跳过")
                await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
                await Config.ToolsConfig.set("GameSign", "ScheduledTime", "")
                return

            # 格式化并合并结果
            formatted = format_sign_results(results)
            Config.ToolsConfig._game_sign_result_data = merge_sign_results(
                Config.ToolsConfig._game_sign_result_data, formatted
            )

            # 清除计划时间
            await Config.ToolsConfig.set("GameSign", "ScheduledTime", "")

            # 检查是否所有用户都已签到，更新全局 LastSignDate
            all_signed_after = True
            for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
                if account.get("GameSignAccount", "Enabled"):
                    if account.get("GameSignAccount", "LastSignDate") != today:
                        all_signed_after = False
                        break
            if all_signed_after:
                await Config.ToolsConfig.set("GameSign", "LastSignDate", today)

            logger.success("游戏社区签到执行完成")

            # 如果启用通知，发送签到结果
            if Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
                from app.tools.game_sign_notify import push_game_sign_notification
                await push_game_sign_notification(results)

        except Exception as e:
            logger.error(f"游戏社区签到执行失败: {e}")
            # 保留已有结果，不覆盖为错误信息
            logger.exception("游戏社区签到执行异常堆栈")

    async def try_game_sign_for_task(self) -> None:
        """任务生命周期触发的游戏签到（跳过已签到用户）

        由定时任务启动、任务结束等事件触发。
        不受全局 LastSignDate 限制，仅按用户 LastSignDate 过滤。
        """
        if not Config.ToolsConfig.get("GameSign", "Enabled"):
            return

        today = datetime.now().strftime("%Y-%m-%d")

        # 快速检查：是否所有用户都已签到
        all_signed = True
        for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
            if account.get("GameSignAccount", "Enabled"):
                if account.get("GameSignAccount", "LastSignDate") != today:
                    all_signed = False
                    break
        if all_signed:
            return

        from app.tools.game_sign import run_all_sign_in, format_sign_results

        try:
            from app.tools.game_sign import merge_sign_results

            results = await run_all_sign_in(force=False)
            if not results:
                return

            formatted = format_sign_results(results)
            Config.ToolsConfig._game_sign_result_data = merge_sign_results(
                Config.ToolsConfig._game_sign_result_data, formatted
            )

            # 签到后检查是否所有用户都已完成
            all_signed_after = True
            for uid, account in Config.ToolsConfig.GameSign_Accounts.items():
                if account.get("GameSignAccount", "Enabled"):
                    if account.get("GameSignAccount", "LastSignDate") != today:
                        all_signed_after = False
                        break
            if all_signed_after:
                await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
                await Config.ToolsConfig.set("GameSign", "ScheduledTime", "")

            logger.info("任务触发的游戏签到已完成")

            if Config.ToolsConfig.get("GameSign", "NotifyEnabled"):
                from app.tools.game_sign_notify import push_game_sign_notification
                await push_game_sign_notification(results)

        except Exception as e:
            logger.error(f"任务触发的游戏签到失败: {e}")


MainTimer = _MainTimer()
