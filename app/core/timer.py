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
from datetime import datetime

from app.services import Matomo
from app.utils import get_logger
from app.utils.constants import UTC8
from app.utils.platform import IS_WINDOWS

from .config import Config
from .community_scheduler import (
    TASK_COMMUNITY_SOURCES,
    CommunityTriggerSource,
    all_community_accounts_signed,
    should_run_community_for_source,
)
from .task_manager import TaskManager

logger = get_logger("主业务定时器")

class _MainTimer:
    def __init__(self):
        self.started = False
        self.second_timer: asyncio.Task[None] | None = None
        self.hour_timer: asyncio.Task[None] | None = None
        self.community_sign_task: asyncio.Task | None = None

    @property
    def game_sign_task(self) -> asyncio.Task | None:
        """兼容旧调用方，返回社区签到后台任务。"""

        return self.community_sign_task

    @game_sign_task.setter
    def game_sign_task(self, task: asyncio.Task | None) -> None:
        self.community_sign_task = task

    async def start(self):
        """启动定时器"""

        if self.started:
            logger.warning("主业务定时器仅能启动一次，无法重复启动")
            return

        self.second_timer = asyncio.create_task(self.second_task())
        self.hour_timer = asyncio.create_task(self.hour_task())
        self.started = True

        if Config.ToolsConfig.get("GameSign", "Enabled") and (
            Config.ToolsConfig.get("GameSign", "RunOnStartup")
        ):
            self.schedule_community_for_startup()

        logger.info("主业务定时器启动")

    async def stop(self):
        """停止定时器"""

        if not self.started:
            return

        tasks = [
            task
            for task in (
                self.second_timer,
                self.hour_timer,
                self.community_sign_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        try:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info("主业务定时器已关闭")
        finally:
            self.started = False

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:
            await self.timed_start()

            if IS_WINDOWS and Config.ToolsConfig.get("ArknightsPC", "Enabled"):
                from app.MaaFW.ArknightWin32 import ArknightWin32Toolkit

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
            # 循环队列由队列项各自的周期驱动，定时设置对它不生效
            if queue.get("Info", "CycleEnabled"):
                continue

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

    def schedule_community_for_startup(self) -> None:
        """Schedule one background community sign-in after application startup."""

        if not (
            Config.ToolsConfig.get("GameSign", "Enabled")
            and (Config.ToolsConfig.get("GameSign", "RunOnStartup"))
        ):
            return

        if (
            self.community_sign_task is not None
            and not self.community_sign_task.done()
        ):
            logger.debug("游戏社区签到后台任务正在执行，跳过重复派发")
            return

        task = asyncio.create_task(self.try_community_for_task(source="startup"))
        self.community_sign_task = task
        task.add_done_callback(self._on_community_sign_done)

    def schedule_game_sign_for_startup(self) -> None:
        """兼容旧调用方，转发到社区签到启动入口。"""

        self.schedule_community_for_startup()

    def _on_community_sign_done(self, task: asyncio.Task) -> None:
        """清理社区签到任务并记录未处理异常。"""

        if self.community_sign_task is task:
            self.community_sign_task = None
        if task.cancelled():
            return

        try:
            task.result()
        except Exception as e:
            logger.error("游戏社区签到后台任务异常", exc_info=e)

    def _on_game_sign_check_done(self, task: asyncio.Task) -> None:
        """兼容旧调用方，转发到社区签到完成回调。"""

        self._on_community_sign_done(task)

    async def _execute_community_sign(
        self, *, source: CommunityTriggerSource = "scheduled"
    ) -> list[dict[str, object]]:
        """执行游戏社区签到并按触发来源决定通知方式。"""
        from app.core.community_sign import (
            CommunitySignInProgressError,
            community_sign_flow,
            run_community_sign_in,
        )
        from app.tools.community import format_community_sign_results

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        try:
            # 流程锁覆盖签到和结果落盘，通知在锁外发送。
            async with community_sign_flow():
                logger.info("开始执行游戏社区签到")
                results = await run_community_sign_in(force=False)

                # 如果所有用户都已签到（无新结果），保留已有结果
                if not results:
                    logger.info("所有用户今日已签到，跳过")
                    if all_community_accounts_signed(
                        Config.ToolsConfig.GameSign_Accounts, today
                    ):
                        await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
                    return []

                # 格式化并合并结果
                formatted = format_community_sign_results(results)
                await Config.update_community_results(formatted)

                # 检查是否所有用户都已签到，更新全局 LastSignDate
                if all_community_accounts_signed(
                    Config.ToolsConfig.GameSign_Accounts, today
                ):
                    await Config.ToolsConfig.set("GameSign", "LastSignDate", today)

            logger.success("游戏社区签到执行完成")

            # 任务触发的结果由任务完成通知消费；其它自动来源单独发送。
            if (
                source not in TASK_COMMUNITY_SOURCES
                and Config.ToolsConfig.get("GameSign", "NotifyEnabled")
            ):
                from app.tools.community_notify import push_community_notification

                try:
                    failed_channels = await push_community_notification(results)
                except Exception as exc:
                    logger.warning(f"游戏社区签到完成，但通知服务异常: {exc}")
                else:
                    if failed_channels:
                        logger.warning(
                            f"游戏社区结果通知部分失败: {'、'.join(failed_channels)}"
                        )
            return results

        except CommunitySignInProgressError:
            logger.info("游戏社区签到正在执行，跳过本次触发")
        except Exception as e:
            logger.error(f"游戏社区签到执行失败: {e}")
            # 保留已有结果，不覆盖为错误信息
            logger.exception("游戏社区签到执行异常堆栈")
        return []

    async def try_community_for_task(
        self, *, source: CommunityTriggerSource | None = None
    ) -> list[dict[str, object]]:
        """执行 MAS 自动签到并返回结果。

        ``task`` 结果由任务完成通知汇总，``startup`` 结果独立通知。
        """
        if source is None:
            source = "task_manual"

        if not should_run_community_for_source(
            enabled=Config.ToolsConfig.get("GameSign", "Enabled"),
            run_on_startup=Config.ToolsConfig.get("GameSign", "RunOnStartup"),
            source=source,
        ):
            return []

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        # 快速检查：是否没有待处理账号
        if all_community_accounts_signed(
            Config.ToolsConfig.GameSign_Accounts, today
        ):
            return []

        return await self._execute_community_sign(source=source)

    async def try_game_sign_for_task(
        self, *, source: CommunityTriggerSource | None = None
    ) -> list[dict[str, object]]:
        """兼容旧调用方，转发到社区签到任务入口。"""

        return await self.try_community_for_task(source=source)


MainTimer = _MainTimer()
