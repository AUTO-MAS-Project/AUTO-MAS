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
from datetime import datetime
from typing import Literal

from app.services import Matomo
from app.MaaFW import ArknightWin32Toolkit
from app.utils.constants import UTC8
from app.utils import get_logger
from .config import Config
from .task_manager import TaskManager


logger = get_logger("主业务定时器")

_GAME_SIGN_TOKEN_FIELDS = ("MiyousheToken", "KuroToken", "SklandToken")
GameSignSource = Literal[
    "scheduled",
    "startup",
    "task_scheduled",
    "task_manual",
    "task_startup",
]
_TASK_GAME_SIGN_SOURCES = {
    "task_scheduled",
    "task_manual",
    "task_startup",
}


def _has_pending_game_sign_account(account, today: str) -> bool:
    """判断账号是否启用、配置了凭据且尚未完成今日签到。"""

    if not account.get("GameSignAccount", "Enabled"):
        return False
    if not any(
        account.get("GameSignAccount", field) for field in _GAME_SIGN_TOKEN_FIELDS
    ):
        return False
    return account.get("GameSignAccount", "LastSignDate") != today


def _all_game_sign_accounts_signed(accounts, today: str) -> bool:
    """判断所有具备凭据的启用账号是否已完成今日签到。"""

    return not any(
        _has_pending_game_sign_account(account, today)
        for _, account in accounts.items()
    )


class _MainTimer:

    def __init__(self):
        self.started = False
        self.second_timer: asyncio.Task[None] | None = None
        self.hour_timer: asyncio.Task[None] | None = None
        self.game_sign_task: asyncio.Task | None = None

    async def start(self):
        """启动定时器"""

        if self.started:
            logger.warning("主业务定时器仅能启动一次，无法重复启动")
            return

        self.second_timer = asyncio.create_task(self.second_task())
        self.hour_timer = asyncio.create_task(self.hour_task())
        self.started = True

        if (
            Config.ToolsConfig.get("GameSign", "Enabled")
            and (
                Config.ToolsConfig.get("GameSign", "RunOnStartup")
            )
        ):
            self.schedule_game_sign_for_startup()

        logger.info("主业务定时器启动")

    async def stop(self):
        """停止定时器"""

        tasks = [
            task
            for task in (
                self.second_timer,
                self.hour_timer,
                self.game_sign_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("主业务定时器已关闭")

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

            await self.timed_start()

            if Config.ToolsConfig.get("ArknightsPC", "Enabled"):
                await ArknightWin32Toolkit.scheduled_task()

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
                        trigger_source="scheduled_task",
                    )
                    await queue.set("Data", "LastTimedStart", curtime)

    def schedule_game_sign_for_startup(self) -> None:
        """Schedule one background sign-in after application startup."""

        if not (
            Config.ToolsConfig.get("GameSign", "Enabled")
            and (
                Config.ToolsConfig.get("GameSign", "RunOnStartup")
            )
        ):
            return

        if self.game_sign_task is not None and not self.game_sign_task.done():
            logger.debug("游戏社区签到后台任务正在执行，跳过重复派发")
            return

        task = asyncio.create_task(self.try_game_sign_for_task(source="startup"))
        self.game_sign_task = task
        task.add_done_callback(self._on_game_sign_check_done)

    def _on_game_sign_check_done(self, task: asyncio.Task) -> None:
        """清理签到任务并记录未处理异常。"""

        if self.game_sign_task is task:
            self.game_sign_task = None
        if task.cancelled():
            return

        try:
            task.result()
        except Exception as e:
            logger.error("游戏社区签到后台任务异常", exc_info=e)

    async def _execute_game_sign(
        self, *, source: GameSignSource = "scheduled"
    ) -> list[dict]:
        """执行游戏签到并按触发来源决定通知方式。"""
        from app.tools.game_sign import (
            GameSignInProgressError,
            format_sign_results,
            game_sign_flow,
            run_all_sign_in,
        )

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        try:
            async with game_sign_flow():
                logger.info("开始执行游戏社区签到")
                results = await run_all_sign_in(force=False)

                # 如果所有用户都已签到（无新结果），保留已有结果
                if not results:
                    logger.info("所有用户今日已签到，跳过")
                    if _all_game_sign_accounts_signed(
                        Config.ToolsConfig.GameSign_Accounts, today
                    ):
                        await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
                    return []

                # 格式化并合并结果
                formatted = format_sign_results(results)
                await Config.update_game_sign_results(formatted)

                # 检查是否所有用户都已签到，更新全局 LastSignDate
                if _all_game_sign_accounts_signed(
                    Config.ToolsConfig.GameSign_Accounts, today
                ):
                    await Config.ToolsConfig.set("GameSign", "LastSignDate", today)

                logger.success("游戏社区签到执行完成")

                # 任务触发的结果由任务完成通知消费；其它自动来源单独发送。
                if (
                    source not in _TASK_GAME_SIGN_SOURCES
                    and Config.ToolsConfig.get("GameSign", "NotifyEnabled")
                ):
                    from app.tools.game_sign_notify import push_game_sign_notification

                    failed_channels = await push_game_sign_notification(results)
                    if failed_channels:
                        logger.warning(
                            f"游戏签到结果通知部分失败: {'、'.join(failed_channels)}"
                        )
                return results

        except GameSignInProgressError:
            logger.info("游戏社区签到正在执行，跳过本次触发")
        except Exception as e:
            logger.error(f"游戏社区签到执行失败: {e}")
            # 保留已有结果，不覆盖为错误信息
            logger.exception("游戏社区签到执行异常堆栈")
        return []

    async def try_game_sign_for_task(
        self, *, source: GameSignSource | None = None
    ) -> list[dict]:
        """执行 MAS 自动签到并返回结果。

        ``task`` 结果由任务完成通知汇总，``startup`` 结果独立通知。
        """
        if source is None:
            source = "task_manual"

        if not Config.ToolsConfig.get("GameSign", "Enabled"):
            return []

        if source == "startup":
            if not Config.ToolsConfig.get("GameSign", "RunOnStartup"):
                return []
        elif source in _TASK_GAME_SIGN_SOURCES and not Config.ToolsConfig.get(
            "GameSign", "ScheduledRun"
        ):
            return []
        elif source not in _TASK_GAME_SIGN_SOURCES:
            return []

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        # 快速检查：是否没有待处理账号
        if _all_game_sign_accounts_signed(
            Config.ToolsConfig.GameSign_Accounts, today
        ):
            return []

        return await self._execute_game_sign(source=source)


MainTimer = _MainTimer()
